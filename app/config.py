"""Configuration loaded from environment variables.

All service URLs and credentials are injected via k8s env vars. The
defaults point at the in-cluster service names so the app runs without
extra config in the cluster.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://marketly:marketly@localhost:5432/checkout"

    # Downstream services
    payments_api_url: str = "http://payments-api.marketly.svc.cluster.local:8080"
    inventory_api_url: str = "http://inventory-api.marketly.svc.cluster.local:8080"
    shipping_api_url: str = "http://shipping-api.marketly.svc.cluster.local:8080"

    # HTTP client
    connect_timeout: float = 30.0
    read_timeout: float = 5.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    model_config = {"env_prefix": "CHECKOUT_", "env_file": ".env"}

settings = Settings()
