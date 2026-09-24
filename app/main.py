"""FastAPI application for the checkout service.

POST /checkout — creates an order, reserves stock, charges the customer,
                 gets a shipping quote, persists the order, returns it.
GET  /health   — liveness probe.
GET  /ready    — readiness probe (checks DB connection).
GET  /orders/{id} — fetch an order by ID.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import UUID

import structlog
import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from app.clients import InventoryClient, PaymentsClient, ShippingClient
from app.config import settings
from app.db import close_pool, get_pool, init_pool, init_schema
from app.models import CheckoutRequest, CheckoutResponse, HealthResponse, Order, OrderItem

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown lifecycle."""
    await init_pool()
    await init_schema()
    logger.info("checkout-api started", port=settings.port)
    yield
    await close_pool()
    logger.info("checkout-api stopped")

app = FastAPI(
    title="checkout-api",
    description="Checkout service for the Marketly e-commerce platform.",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()

@app.get("/ready")
async def ready() -> dict:
    """Readiness probe — checks the DB pool is alive."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(e)},
        )

@app.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(req: CheckoutRequest) -> CheckoutResponse:
    """Process a checkout request.

    Flow:
      1. For each item, get the price + reserve stock from inventory-api.
      2. Get a shipping quote from shipping-api.
      3. Charge the customer via payments-api.
      4. Confirm the stock reservations (decrement actual stock).
      5. Persist the order to Postgres.
      6. Return the order + payment_id + tracking_number.
    """
    logger.info("checkout started", customer=req.customer_email, items=len(req.items))

    inventory = InventoryClient()
    payments = PaymentsClient()
    shipping = ShippingClient()

    try:
        # 1. Reserve stock + collect prices.
        order_items: list[OrderItem] = []
        for item in req.items:
            product = inventory.get_price(item.sku)
            inventory.reserve(item.sku, item.quantity)
            order_items.append(
                OrderItem(
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price_cents=product["price_cents"],
                )
            )

        subtotal = sum(i.unit_price_cents * i.quantity for i in order_items)

        # 2. Shipping quote.
        quote = shipping.quote(req.shipping_address, req.items)
        shipping_cents = quote["shipping_cents"]

        # 3. Charge the customer.
        total = subtotal + shipping_cents
        payment = payments.charge(
            amount_cents=total,
            customer_email=str(req.customer_email),
            order_id="",  # filled in after we create the order
        )

        # 4. Build the order.
        order = Order(
            customer_email=req.customer_email,
            items=order_items,
            subtotal_cents=subtotal,
            shipping_cents=shipping_cents,
            total_cents=total,
            payment_id=payment.get("payment_id"),
            tracking_number=quote.get("tracking_number"),
        )

        # 5. Confirm stock (decrement actual stock now that payment succeeded).
        for item in req.items:
            inventory.confirm(item.sku, item.quantity)

        # 6. Persist.
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO orders (id, customer_email, items, subtotal_cents,
                                    shipping_cents, total_cents, status,
                                    payment_id, tracking_number, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                order.id,
                str(order.customer_email),
                json.dumps([i.model_dump() for i in order.items]),
                order.subtotal_cents,
                order.shipping_cents,
                order.total_cents,
                order.status,
                order.payment_id,
                order.tracking_number,
                order.created_at,
            )

        logger.info(
            "checkout completed",
            order_id=str(order.id),
            total_cents=total,
            payment_id=order.payment_id,
        )

        return CheckoutResponse(
            order=order,
            payment_id=order.payment_id,
            tracking_number=order.tracking_number,
        )

    except httpx.HTTPStatusError as e:
        logger.error("checkout failed", error=str(e), customer=req.customer_email)
        if e.response.status_code == 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"shipping quote failed: {e.response.text}",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"checkout failed: {e}",
            )
    except Exception as e:
        logger.error("checkout failed", error=str(e), customer=req.customer_email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"checkout failed: {e}",
        )
    finally:
        inventory.close()
        payments.close()
        shipping.close()

@app.get("/orders/{order_id}", response_model=CheckoutResponse)
async def get_order(order_id: UUID) -> CheckoutResponse:
    """Fetch an order by ID."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        if row is None:
            raise HTTPException(status_code=404, detail="order not found")

        items = [OrderItem(**i) for i in json.loads(row["items"])]
        order = Order(
            id=row["id"],
            customer_email=row["customer_email"],
            items=items,
            subtotal_cents=row["subtotal_cents"],
            shipping_cents=row["shipping_cents"],
            total_cents=row["total_cents"],
            status=row["status"],
            payment_id=row["payment_id"],
            tracking_number=row["tracking_number"],
            created_at=row["created_at"],
        )
        return CheckoutResponse(order=order)
