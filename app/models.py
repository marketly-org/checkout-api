"""Pydantic models for request and response bodies."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field

class CheckoutItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(..., ge=1, le=100)

class CheckoutRequest(BaseModel):
    customer_email: EmailStr
    items: list[CheckoutItem] = Field(..., min_items=1, max_items=50)
    shipping_address: str = Field(..., min_length=1, max_length=500)

class OrderItem(BaseModel):
    sku: str
    quantity: int
    unit_price_cents: int

class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    customer_email: EmailStr
    items: list[OrderItem]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    status: str = "confirmed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CheckoutResponse(BaseModel):
    order: Order
    payment_id: str | None = None
    tracking_number: str | None = None

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "checkout-api"
    version: str = "1.0.0"
