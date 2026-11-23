import httpx
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

from action_agent.main import create_app


async def test_the_app_is_wrapped_and_untraced_without_a_connection_string(monkeypatch):
    monkeypatch.setenv("ADAPTERS", "fake")
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    app = create_app()
    assert isinstance(app, OpenTelemetryMiddleware)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
        assert (await c.post("/", json={})).status_code == 401
