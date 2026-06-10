from pydantic import BaseModel
from typing import List, Optional

from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./payments.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class PaymentRequest(BaseModel):
    merchant_id: str
    amount: int
    currency: str
    method: str
    card_holder: str

class PaymentResponse(BaseModel):
    transaction_id: str
    status: str
    amount: Optional[float] = None       # ДОБАВЛЕНО В API CONTRACT
    currency: Optional[str] = None       # ДОБАВЛЕНО В API CONTRACT
    card_holder: Optional[str] = None    # ДОБАВЛЕНО В API CONTRACT
    redirect_url: Optional[str] = None

class WebhookPayload(BaseModel):
    transaction_id: str
    event: str

class TransactionListResponse(BaseModel):
    total_count: int
    transactions: List[dict]

class TransactionDB(Base):
    __tablename__ = "transactions"
    
    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="pending")
    merchant_id = Column(String)
    amount = Column(Integer)  # Или Float, в зависимости от структуры
    currency = Column(String)
    card_holder = Column(String)  # ДОБАВЛЕНО В БД