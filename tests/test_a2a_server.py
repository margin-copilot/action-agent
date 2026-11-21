"""The A2A server in one process: real a2a-sdk client, real tokens, the shared reply contract."""

import asyncio

import httpx
import pytest
from a2a.client import ClientCallContext, ClientConfig, create_client
from a2a.client.errors import A2AClientError
from a2a.helpers import get_data_parts, new_text_message
from a2a.types import Role, SendMessageRequest
from a2a.utils.errors import A2AError
from margin_copilot_shared.testing.issuer import LocalIssuer

from action_agent.adapters.inbound.a2a_server import create_a2a_app
from action_agent.application.drafts import FakeDrafter

ACTION_AGENT = "action-agent-client-id"
ORCHESTRATOR = "orchestrator-client-id"
URL = "http://action-agent/"


@pytest.fixture
def issuer():
    return LocalIssuer()


class BrokenDrafter:
    async def reply(self, question):
        raise RuntimeError("Divide by zero error encountered. (8134)")


def serve(issuer, drafter):
    validator = issuer.validator(audience=ACTION_AGENT, allowed_callers=frozenset({ORCHESTRATOR}))
    app = create_a2a_app(drafter, validator, URL)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app))


@pytest.fixture
def http(issuer):
    return serve(issuer, FakeDrafter())


async def send(http, token):
    config = ClientConfig(httpx_client=http, streaming=False)
    client = await create_client(URL, client_config=config)
    request = SendMessageRequest(
        message=new_text_message("Draft a 2% increase for UHT milk 1 L.", role=Role.ROLE_USER)
    )
    context = ClientCallContext(service_parameters={"Authorization": f"Bearer {token}"})
    async for event in client.send_message(request, context=context):
        if event.WhichOneof("payload") == "message":
            return get_data_parts(event.message.parts)
    return None


def reply(oid):
    return [{"answer": f"fake action-agent drafts as user {oid}", "refusal": None, "citations": []}]


async def test_the_reply_is_one_data_part_in_the_shared_contract(issuer, http):
    token = issuer.issue(audience=ACTION_AGENT, azp=ORCHESTRATOR, oid="north-mgr")
    assert await send(http, token) == reply("north-mgr")


async def test_a_failure_reaches_the_caller_as_a_fixed_message(issuer):
    token = issuer.issue(audience=ACTION_AGENT, azp=ORCHESTRATOR, oid="north-mgr")
    with pytest.raises(A2AError) as failed:
        await send(serve(issuer, BrokenDrafter()), token)
    assert "action-agent failed" in str(failed.value)
    assert "8134" not in str(failed.value)


async def test_concurrent_callers_each_see_themselves(issuer, http):
    oids = [f"user-{n}" for n in range(10)]
    tokens = [issuer.issue(audience=ACTION_AGENT, azp=ORCHESTRATOR, oid=oid) for oid in oids]
    replies = await asyncio.gather(*(send(http, token) for token in tokens))
    assert replies == [reply(oid) for oid in oids]


async def test_token_from_an_unlisted_caller_is_403(issuer, http):
    token = issuer.issue(audience=ACTION_AGENT, azp="cli-client-id")
    with pytest.raises(A2AClientError, match="403"):
        await send(http, token)


async def test_token_for_another_service_is_401(issuer, http):
    token = issuer.issue(audience=ORCHESTRATOR, azp=ORCHESTRATOR)
    with pytest.raises(A2AClientError, match="401"):
        await send(http, token)


async def test_agent_card_needs_no_token(http):
    response = await http.get(f"{URL}.well-known/agent-card.json")
    assert response.status_code == 200
    assert response.json()["name"] == "action-agent"
