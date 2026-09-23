"""Unit tests for the checkout-api.

These tests use httpx's MockTransport to stub out downstream HTTP calls
so the test suite runs without real infrastructure. The tests pass even
because the issue only manifests under
real network latency + load.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Test client with the DB layer mocked out.

    main.py imports init_pool/init_schema/close_pool/get_pool from app.db
    into its own namespace, so we patch them where they are USED
    (app.main) — otherwise the lifespan would open a real asyncpg pool
    and the handlers would use unmocked references.
    """
    from app.main import app

    with patch("app.main.init_pool"), \
         patch("app.main.init_schema"), \
         patch("app.main.close_pool"), \
         patch("app.main.get_pool") as mock_pool:
        conn = mock_pool.return_value.acquire.return_value.__aenter__.return_value
        conn.execute = pytest.mock_async
        with TestClient(app) as c:
            yield c


def test_health(client):
    """Health endpoint returns 200 + service name."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "checkout-api"

def test_checkout_requires_items(client):
    """Checkout with empty items list returns 422."""
    resp = client.post(
        "/checkout",
        json={
            "customer_email": "test@example.com",
            "items": [],
            "shipping_address": "123 Main St",
        },
    )
    assert resp.status_code == 422
