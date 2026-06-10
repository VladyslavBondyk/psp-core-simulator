import time
import uuid
import hmac
import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse
from models import PaymentRequest, PaymentResponse, WebhookPayload, TransactionListResponse
from models import TransactionDB, SessionLocal, engine, Base
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

# Инициализация таблиц базы данных при старте приложения
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fintech Core API Simulator",
    description="Production-ready core payment gateway engine simulating PSP transaction processing.",
    version="1.0.0"
)

# Хранилище лимитов запросов (In-Memory Rate Limiting Cache)
request_counts = {}
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60

# Секретный ключ шлюза для генерации и сверки цифровых подписей вебхуков
WEBHOOK_SECRET = "wh_sec_12345"

# Локальный кэш идемпотентности для предотвращения дублирования списаний
idempotency_cache = {}

# Защищенное хранилище активных токенов авторизации мерчантов (В проде заменяется на СУБД)
VALID_API_KEYS = {"sk_test_12345abcde"}


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """
    HTTP Middleware для сквозного трекинга транзакционного потока.
    Использует Correlation ID для связывания логов фронтенда, бэкенда и внешних банковских ответов.
    """
    # Проверяем, передал ли мерчант свой ID, иначе генерируем UUID для трассировки инцидентов
    correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    
    # Сохраняем ID в контекст состояния запроса для использования во внутренних логах
    request.state.correlation_id = correlation_id
    
    # Передаем запрос дальше по цепочке обработки
    response = await call_next(request)
    
    # Инжектируем ID в исходящие заголовки для клиентского трекинга и триажа саппортом
    response.headers["X-Request-ID"] = correlation_id
    return response


def get_db():
    """
    Генератор сессий SQLAlchemy (Dependency Injection).
    Гарантирует изоляцию транзакций БД и обязательное закрытие коннекта после ответа API.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def enforce_rate_limit(x_api_key: str = Header(default=None)):
    """
    Компонент защиты инфраструктуры шлюза от DDoS и Card-Checking (Брутфорса карт).
    Ограничивает количество запросов в фиксированном временном окне для каждого API Key.
    """
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        return 
        
    current_time = time.time()
    
    if x_api_key not in request_counts:
        request_counts[x_api_key] = {"count": 1, "start_time": current_time}
        return
        
    client_data = request_counts[x_api_key]
    
    # Сброс окна лимитов по истечении интервала
    if current_time - client_data["start_time"] > RATE_LIMIT_WINDOW:
        request_counts[x_api_key] = {"count": 1, "start_time": current_time}
        return
        
    # Блокировка клиента при превышении порога безопасности (HTTP 429)
    if client_data["count"] >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too Many Requests: Rate limit exceeded")
        
    client_data["count"] += 1


def verify_api_key(x_api_key: str = Header(default=None)):
    """
    Слой Server-to-Server аутентификации мерчанта.
    Проверяет секретный токен доступа в заголовках HTTP-запроса.
    """
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key") 


@app.post(
    "/api/v1/payments/authorize", 
    response_model=PaymentResponse, 
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)]
)
async def authorize_payment(
    req: PaymentRequest, 
    request: Request,
    db: Session = Depends(get_db), 
    idempotency_key: str = Header(default=None)
):
    """
    Инициация и авторизация платежной транзакции (Payment Transaction Process).
    Проверяет лимиты, защищает от повторных списаний и фиксирует состояние в реестре.
    """
    # Защита от дублирования платежей (Idempotency Check)
    if idempotency_key and idempotency_key in idempotency_cache:
        return idempotency_cache[idempotency_key]

    txn_id = str(uuid.uuid4())
    
    try:
        # ТРИАЖ И ТЕСТИРОВАНИЕ: Симуляция критических инфраструктурных сбоев
        if req.amount == 999:
            # Имитация уникального конфликта БД или повторного нарушения ограничений схемы
            raise IntegrityError("Simulated Constraint Violation", params=None, orig=None)
        if req.amount == 888:
            # Имитация падения СУБД / Таймаута дисковой подсистемы банка-эквайера
            raise OperationalError("Simulated DB Unresponsive", params=None, orig=None)

        # Сохранение транзакции со статусом 'authorized' в постоянное хранилище
        new_txn = TransactionDB(
            id=txn_id, 
            status="authorized", 
            merchant_id=req.merchant_id, 
            amount=req.amount,
            currency=req.currency,
            card_holder=req.card_holder  # Передаем из запроса в БД
        )
        db.add(new_txn)
        db.commit()
        
    except IntegrityError as e:
        db.rollback()  # Откат транзакции во избежание деградации данных
        print(f"[{request.state.correlation_id}] DIAGNOSTIC: Constraint Violation: {e}")
        raise HTTPException(status_code=400, detail="Transaction conflict: Idempotency or Unique constraint violation")
        
    except OperationalError as e:
        db.rollback()
        print(f"[{request.state.correlation_id}] DIAGNOSTIC: DB Unresponsive/Disk Full: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable: Database infrastructure issue")
        
    except Exception as e:
        db.rollback()
        print(f"[{request.state.correlation_id}] DIAGNOSTIC: Unexpected Bug: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
    response_data = PaymentResponse(
        transaction_id=txn_id, 
        status="authorized",
        amount=req.amount,
        currency=req.currency,
        card_holder=req.card_holder
    )
    
    # Кэшируем успешный ответ для последующих запросов с этим же ключом идемпотентности
    if idempotency_key:
        idempotency_cache[idempotency_key] = response_data
        
    return response_data


@app.post("/api/v1/payments/{transaction_id}/capture")
async def capture_payment(transaction_id: str, db: Session = Depends(get_db)):
    """
    Клиринг (Capture) платежа. 
    Переводит транзакцию из состояния холдирования (authorized) в финальное списание (settled).
    """
    txn = db.query(TransactionDB).filter(TransactionDB.id == transaction_id).first()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    if txn.status != "authorized":
        raise HTTPException(status_code=400, detail="Transaction not in authorized state")
        
    txn.status = "settled"
    db.commit()
    return {"transaction_id": transaction_id, "status": "settled"}


@app.get("/api/v1/payments/{transaction_id}", response_model=PaymentResponse)
async def get_payment_status(
    transaction_id: str, 
    db: Session = Depends(get_db), 
    x_api_key: str = Header(default=None)
):
    """
    Запрос статуса транзакции (Чтение/Polling).
    Возвращает актуальный статус платежа из реестра БД. Безопасный метод (Idempotent).
    """
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")
        
    txn = db.query(TransactionDB).filter(TransactionDB.id == transaction_id).first()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    # Извлекаем данные из БД и маппим в ответ (Строго 4 пробела отступа от края функции)
    return PaymentResponse(
        transaction_id=txn.id, 
        status=txn.status,
        amount=txn.amount,
        currency=txn.currency,
        card_holder=txn.card_holder,
        redirect_url=None
    )


@app.post("/api/v1/payments/{transaction_id}/refund")
async def refund_payment(transaction_id: str, db: Session = Depends(get_db)):
    """
    Инициация процедуры мирного возврата средств (Refund).
    Добровольное списание со счета мерчанта для возврата покупателю.
    """
    txn = db.query(TransactionDB).filter(TransactionDB.id == transaction_id).first()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    txn.status = "refunded"
    db.commit()
    return {"transaction_id": transaction_id, "status": "refunded"}


@app.post("/api/webhooks/status_update")
async def receive_webhook(
    request: Request, 
    payload: WebhookPayload, 
    db: Session = Depends(get_db), 
    x_webhook_signature: str = Header(default=None)
):
    """
    Асинхронный прием уведомлений (Webhook Ingress).
    Защищен криптографической верификацией HMAC-SHA256 для предотвращения подделки статусов платежей.
    """
    raw_body = await request.body()
    
    # Генерация эталонной сигнатуры на основе секретного ключа и сырого тела запроса
    expected_sig = hmac.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    
    # Сверка подписей алгоритмом с защитой от атак по времени (Timing Attacks)
    if not x_webhook_signature or not hmac.compare_digest(expected_sig, x_webhook_signature):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid webhook signature")
    
    txn = db.query(TransactionDB).filter(TransactionDB.id == payload.transaction_id).first()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    # Обновление финансового статуса на основе подтвержденного внешнего события (например, chargeback)
    txn.status = payload.event
    db.commit()
    
    return {"message": "Webhook processed", "updated_status": payload.event}


@app.get("/api/v1/payments", response_model=TransactionListResponse)
async def list_payments(
    status: Optional[str] = None, 
    limit: int = 10, 
    x_api_key: str = Header(default=None),
    db: Session = Depends(get_db)
):
    """
    Выгрузка реестра транзакций мерчанта с поддержкой фильтрации по статусу платежа.
    Используется для построения финансовых отчетов, сверки и дашбордов поддержки.
    """
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")
        
    query = db.query(TransactionDB)
    
    if status:
        query = query.filter(TransactionDB.status == status)
        
    txns = query.limit(limit).all()
    
    # Включаем card_holder в выгрузку списков для поддержки
    results = [{
        "transaction_id": txn.id, 
        "status": txn.status, 
        "merchant_id": txn.merchant_id, 
        "amount": txn.amount,
        "currency": txn.currency,
        "card_holder": txn.card_holder
    } for txn in txns]
            
    return {"total_count": len(results), "transactions": results}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Глобальный перехватчик необработанных критических исключений (Global Exception Handler).
    Логирует детали сбоя для внутренней команды инженеров, скрывая сырые трейсы от внешних пользователей.
    """
    print(f"CRITICAL SYSTEM ERROR: {exc}")
    
    # Маскирование системных уязвимостей и выдача безопасного общего JSON-ответа клиенту (PCI-DSS требование)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "message": "An unexpected error occurred. Please contact support."}
    )