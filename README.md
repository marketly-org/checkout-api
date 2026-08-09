# checkout-api

Checkout service for the **Marketly** e-commerce platform.

Handles the checkout flow: stock reservation → payment → shipping quote → order persistence.

## Stack

- **Python 3.12** + **FastAPI** 0.115
- **asyncpg** for non-blocking Postgres access
- **httpx** for downstream HTTP calls
- **structlog** for structured logging

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/checkout` | Process a checkout request |
| GET | `/orders/{id}` | Fetch an order by ID |
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks DB) |

## Downstream dependencies

- `inventory-api` — stock reservation + pricing
- `payments-api` — customer charging
- `shipping-api` — shipping quotes + tracking

## Local development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Tests

```bash
pytest tests/ -v
```
