"""Composition root. ADAPTERS=azure|fake picks the adapters; there is no default."""

import os

import httpx
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import ManagedIdentityCredential
from margin_copilot_shared.security.obo import OboClient, managed_identity_assertion
from margin_copilot_shared.security.tokens import entra_validator
from margin_copilot_shared.testing.issuer import LocalIssuer
from starlette.applications import Starlette

from action_agent.adapters.inbound.a2a_server import create_a2a_app
from action_agent.adapters.outbound.extractor import FoundryExtractor
from action_agent.adapters.outbound.proposals_client import HttpProposals
from action_agent.application.drafts import Drafter, FakeDrafter

MODEL_TIMEOUT = 60
PROPOSALS_TIMEOUT = 150  # proposals-api may scale from zero and wake the database


def create_app() -> Starlette:
    env = os.environ
    adapters = env["ADAPTERS"]
    if adapters == "azure":
        tenant_id, client_id, identity = env["TENANT_ID"], env["CLIENT_ID"], env["AZURE_CLIENT_ID"]
        callers = frozenset(env["ALLOWED_CALLERS"].split(","))
        model = FoundryChatClient(
            project_endpoint=env["FOUNDRY_PROJECT_ENDPOINT"],
            model=env["FOUNDRY_MODEL"],
            credential=ManagedIdentityCredential(client_id=identity),
            timeout=MODEL_TIMEOUT,
        )
        obo = OboClient(tenant_id, client_id, managed_identity_assertion(identity))
        proposals = HttpProposals(
            env["PROPOSALS_API_URL"],
            env["PROPOSALS_API_SCOPE"],
            obo.exchange,
            httpx.AsyncClient(timeout=PROPOSALS_TIMEOUT),
        )
        validator = entra_validator(tenant_id, client_id, callers)
        drafter = Drafter(FoundryExtractor(model), proposals)
        return create_a2a_app(drafter, validator, env["PUBLIC_URL"])
    if adapters == "fake":
        # A fresh in-memory key per process: nobody outside this process can mint a token for it.
        validator = LocalIssuer().validator(
            audience="action-agent", allowed_callers=frozenset({"orchestrator"})
        )
        public_url = env.get("PUBLIC_URL", "http://localhost:8000/")
        return create_a2a_app(FakeDrafter(), validator, public_url)
    raise ValueError(f"ADAPTERS must be azure or fake, not {adapters!r}")
