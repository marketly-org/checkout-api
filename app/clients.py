"""HTTP clients for downstream services.

The checkout-api talks to three downstream services:
  - inventory-api: reserve + confirm stock
  - payments-api: charge the customer
  - shipping-api: get a shipping quote + tracking number

All three are called synchronously during checkout. If any of them is slow,
the checkout request blocks until the downstream responds (or the TCP
connection times out at the OS level, which is ~2 minutes on Linux).
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.models import CheckoutItem


class InventoryClient:
    """Client for the inventory-api service."""

    def __init__(self) -> None:
        self._base_url = settings.inventory_api_url
        # NOTE: httpx.Client with no timeout uses the default 5s. But we're
        # using httpx.Client() without any timeout= kwarg, which means it
        # falls back to httpx's default (5s connect + 5s read). That should
        # be fine for normal operation, but when payments-api gets rate-
        # limited by Stripe and starts holding connections open, the
        # inventory-api calls to it (for stock confirmation) pile up too.
        # The real fix is to set an explicit, shorter timeout so we fail
        # fast and don't exhaust our connection pool.
        self._client = httpx.Client()

    def reserve(self, sku: str, quantity: int) -> dict:
        """Reserve stock for an item. Raises httpx.HTTPError on failure."""
        resp = self._client.post(
            f"{self._base_url}/reserve",
            json={"sku": sku, "quantity": quantity},
        )
        resp.raise_for_status()
        return resp.json()

    def confirm(self, sku: str, quantity: int) -> dict:
        """Confirm a stock reservation (decrements actual stock)."""
        resp = self._client.post(
            f"{self._base_url}/confirm",
            json={"sku": sku, "quantity": quantity},
        )
        resp.raise_for_status()
        return resp.json()

    def get_price(self, sku: str) -> dict:
        """Get the current price for a SKU."""
        resp = self._client.get(f"{self._base_url}/products/{sku}")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


class PaymentsClient:
    """Client for the payments-api service."""

    def __init__(self) -> None:
        self._base_url = settings.payments_api_url
        # Same issue as InventoryClient — no explicit timeout. When the
        # payments-api is slow (Stripe rate limiting), these calls block
        # indefinitely, exhausting the checkout-api's thread pool.
        self._client = httpx.Client()

    def charge(self, amount_cents: int, customer_email: str, order_id: str) -> dict:
        """Charge a customer. Returns the payment_id."""
        resp = self._client.post(
            f"{self._base_url}/charge",
            json={
                "amount_cents": amount_cents,
                "customer_email": customer_email,
                "order_id": order_id,
                "currency": "USD",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


class ShippingClient:
    """Client for the shipping-api service."""

    def __init__(self) -> None:
        self._base_url = settings.shipping_api_url
        self._client = httpx.Client()

    def quote(self, address: str, items: list[CheckoutItem]) -> dict:
        """Get a shipping quote for an order."""
        resp = self._client.post(
            f"{self._base_url}/quote",
            json={
                "address": address,
                "items": [{"sku": i.sku, "quantity": i.quantity} for i in items],
            },
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()
