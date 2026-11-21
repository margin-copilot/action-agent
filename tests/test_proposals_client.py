import json
from decimal import Decimal

import httpx
import pytest
from margin_copilot_shared.contracts import DraftRequest
from margin_copilot_shared.security.context import RequestContext, request_scope
from margin_copilot_shared.security.tokens import Caller

from action_agent.adapters.outbound.proposals_client import HttpProposals, ProposalsFailed
from action_agent.application.drafts import DraftRejected
from tests.test_wording import proposal

USER = RequestContext(Caller("north-mgr", "tid", "orchestrator", frozenset()), token="user-token")
SCOPE = "api://proposals-api/access_as_user"
REQUEST = DraftRequest(product="UHT milk 1 L", region="N", new_price=Decimal("7.25"))


def client(status, body, seen=None, exchanges=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        return httpx.Response(status, content=payload)

    def exchange(token, scopes):
        if exchanges is not None:
            exchanges.append((token, list(scopes)))
        return "proposals-token"

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpProposals("http://proposals-api/", SCOPE, exchange, http)


async def test_each_draft_exchanges_the_callers_token_for_the_proposals_scope():
    seen, exchanges = [], []
    proposals = client(201, proposal().model_dump(mode="json"), seen, exchanges)
    with request_scope(USER):
        assert await proposals.draft(REQUEST) == proposal()
        await proposals.draft(REQUEST)
    assert exchanges == [("user-token", [SCOPE])] * 2
    assert str(seen[0].url) == "http://proposals-api/drafts"
    assert seen[0].headers["authorization"] == "Bearer proposals-token"
    assert json.loads(seen[0].content) == {
        "product": "UHT milk 1 L",
        "region": "N",
        "new_price": "7.25",
        "change_pct": None,
    }


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in proposal().model_dump(mode="json").items() if k != "approver"},
        proposal(status="approved").model_dump(mode="json"),
    ],
)
async def test_a_201_must_be_a_pending_proposal(body):
    with request_scope(USER), pytest.raises(Exception):  # noqa: B017
        await client(201, body).draft(REQUEST)


async def test_error_bodies_are_validated():
    with request_scope(USER), pytest.raises(DraftRejected) as rejected:
        await client(403, {"error": "region not allowed"}).draft(REQUEST)
    assert (rejected.value.status, rejected.value.error.error) == (403, "region not allowed")
    with request_scope(USER), pytest.raises(Exception):  # noqa: B017
        await client(404, {"error": "x", "secret": "y"}).draft(REQUEST)


@pytest.mark.parametrize(("status", "body"), [(500, b"oops"), (201, b"x" * 70_000)])
async def test_other_replies_fail(status, body):
    with request_scope(USER), pytest.raises(ProposalsFailed):
        await client(status, body).draft(REQUEST)
