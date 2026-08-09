"""Pytest configuration + shared fixtures."""
import pytest


class AsyncMock:
    """Minimal async mock for methods that return awaitables."""

    def __init__(self, *args, **kwargs):
        self.return_value = kwargs.get("return_value")

    def __await__(self):
        async def _():
            return self.return_value
        return _().__await__()


@pytest.fixture
def mock_async():
    return AsyncMock
