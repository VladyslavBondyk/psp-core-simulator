# Fintech Core API Simulator (PSP Engine)

A production-ready, high-performance Payment Service Provider (PSP) gateway simulator built with Python and FastAPI. This engine demonstrates industry-standard transaction processing lifecycles, rigorous server-to-server security protocols, robust error triage, and strict schema validation.

Designed to illustrate modern payment gateway architectures, handling data persistence with SQLite and implementing protective layers against infrastructure vulnerabilities and malicious card exploits.

## 🚀 Key Architectural Features

* **Advanced Transaction Ledger:** Implements a strict dual-state authorization model (`Pending` -> `Authorized` / `Failed`) with comprehensive metadata collection, preserving financial data footprints (`amount`, `currency`, `card_holder`).
* **S2S Authentication Middleware:** Validates incoming requests using secure merchant server keys (`sk_test_...`) passed via HTTP headers to isolate tenant access.
* **Idempotency & Resilience Layer:** Intercepts redundant transaction payloads to block duplicate card charges, logging state alterations tied directly to a distributed tracing `X-Request-ID`.
* **Rate-Limiting Protection:** Integrated defensive middleware blocking brute-force card checking and rapid automated fraud scripts by enforcing request velocity thresholds.
* **HMAC-SHA256 Webhook Ingress:** Secures asynchronous payment event delivery (e.g., chargebacks) via cryptographic signature verifications to protect ledger integrity against spoofing.

----------------------------------------------------

## 🛠️ Tech Stack & Ecosystem

* **Core Framework:** FastAPI (Python 3.10+)
* **Data Persistence:** SQLAlchemy ORM / SQLite
* **Validation Engine:** Pydantic v2 (Strict data contract governance)
* **Testing Infrastructure:** Postman Client / cURL

-------------------------------------------------

## 💻 Installation & Local Deployment

### 1. Clone the Architecture
```bash
git clone [https://github.com/YOUR_USERNAME/psp-core-simulator.git](https://github.com/YOUR_USERNAME/psp-core-simulator.git)
cd psp-core-simulator
```
2. Isolate Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```
3. Install Dependencies
```bash
pip install fastapi uvicorn sqlalchemy pydantic
```
4. Boot the Core Gateway
```bash
uvicorn main:app --reload
```

The gateway initializes a local database file payments.db and binds to: http://127.0.0.1:8000

🔌 Core API Specifications
1. Authorize Payment
•	Method: POST
•	Path: /api/v1/payments/authorize
•	Headers:
•	X-API-Key: sk_test_12345abcde (Required)
•	Idempotency-Key: unique-uuid-string-12345 (Recommended)
•	Content-Type: application/json
•	Request Payload (JSON Body):
```json
{
  "merchant_id": "WRO_paytech",
  "amount": 150.50,
  "currency": "USD",
  "card_holder": "John Doe"
}
```
•	Successful Response (200 OK):
```json
{
  "transaction_id": "49488f32-fa41-4590-9ff1-3f3106878c4c",
  "status": "authorized",
  "amount": 150.50,
  "currency": "USD",
  "card_holder": "John Doe",
  "redirect_url": null
}
```
2. Get Payment Status (Polling/Inspection)
•	Method: GET
•	Path: /api/v1/payments/{transaction_id}
•	Headers:
•	X-API-Key: sk_test_12345abcde
•	Response Payload (200 OK):
```json
{
  "transaction_id": "49488f32-fa41-4590-9ff1-3f3106878c4c",
  "status": "authorized",
  "amount": 150.50,
  "currency": "USD",
  "card_holder": "John Doe",
  "redirect_url": null
}
```

3. Capture Payment (Settlement Trigger)
•	Method: POST
•	Path: /api/v1/payments/{transaction_id}/capture
•	Response Payload (200 OK):
```json
{
  "transaction_id": "49488f32-fa41-4590-9ff1-3f3106878c4c",
  "status": "settled"
}
```
-------------------------------------------------
🔍 Triage, Logging, and Error Governance
The engine isolates system exceptions from customer-facing API responses. Low-level database faults and infrastructure crashes are captured, bound to the transaction's X-Request-ID (Correlation ID) inside internal logs, and safely abstracted to comply with PCI-DSS guidelines.

API Error Mapping Matrix
| HTTP Status | Error Context | Core Trigger Condition / Log Signal | Client-Facing Message |
| :--- | :--- | :--- | :--- |
| **`400 Bad Request`** | Data Conflict / Schema Breach | `IntegrityError` or missing structural fields (e.g., `card_holder`). | *Transaction conflict: Idempotency or Unique constraint violation* |
| **`401 Unauthorized`** | Key/Signature Invalidation | Rogue header input or mismatched HMAC signature during webhook delivery. | *Unauthorized: Invalid API Key / Webhook signature* |
| **`429 Too Many Requests`** | Velocity Breach | Rate-limiter cache exceeds `10` requests per window from a single API key. | *Too Many Requests: Rate limit exceeded* |
| **`503 Service Unavailable`** | Infrastructure Timeout | `OperationalError` triggered via backend database lock/unresponsiveness. | *Service Unavailable: Database infrastructure issue* |


📈 Engineering Roadmap
	1.	Tokenization Vault (PCI-DSS): Decouple raw cardholder details into placeholder tokens using asymmetric encryption keys.
	2.	Asynchronous Batch Settlement: Implement background workers to group Captured states into clearing batches for automated bank processing files.
	3.	Dynamic Routing: Add backup acquirer profiles to automatically route transactions if primary processing endpoints trigger mock 503 errors.

