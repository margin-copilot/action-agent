from types import SimpleNamespace

import httpx
import pytest

from action_agent.main import create_app


async def test_fake_mode_serves_the_card_and_requires_tokens(monkeypatch):
    monkeypatch.setenv("ADAPTERS", "fake")
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
        assert (await c.get("/.well-known/agent-card.json")).status_code == 200
        assert (await c.post("/", json={})).status_code == 401


AZURE = {
    "ADAPTERS": "azure",
    "TENANT_ID": "11111111-1111-1111-1111-111111111111",
    "CLIENT_ID": "action-agent-client-id",
    "AZURE_CLIENT_ID": "managed-identity-client-id",
    "ALLOWED_CALLERS": "orchestrator-client-id",
    "PUBLIC_URL": "http://action-agent/",
    "PROPOSALS_API_URL": "http://proposals-api/",
    "PROPOSALS_API_SCOPE": "api://proposals-api-client-id/access_as_user",
    "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/example",
    "FOUNDRY_MODEL": "gpt-5-mini",
}


@pytest.fixture
def azure_env(monkeypatch):
    for name, value in AZURE.items():
        monkeypatch.setenv(name, value)
    # msal reaches out at construction
    monkeypatch.setattr("action_agent.main.OboClient", lambda *args: SimpleNamespace(exchange=None))


def test_azure_mode_composes(azure_env):
    assert create_app() is not None


@pytest.mark.parametrize("missing", sorted(set(AZURE) - {"ADAPTERS"}))
def test_azure_mode_has_no_defaults(azure_env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(KeyError):
        create_app()


def test_adapters_must_be_set_explicitly(monkeypatch):
    monkeypatch.delenv("ADAPTERS", raising=False)
    with pytest.raises(KeyError):
        create_app()
    monkeypatch.setenv("ADAPTERS", "prod")
    with pytest.raises(ValueError, match="azure or fake"):
        create_app()


def test_the_proposals_timeout_covers_a_cold_start():
    from action_agent.main import PROPOSALS_TIMEOUT

    # proposals-api scaling from zero (~40 s) plus the free database waking up (up to ~65 s), but
    # under the orchestrator's 200 s wait for this agent.
    assert 120 <= PROPOSALS_TIMEOUT < 200
