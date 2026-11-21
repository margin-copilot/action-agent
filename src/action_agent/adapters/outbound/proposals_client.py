"""Proposals port adapter: POST /drafts on proposals-api with a fresh on-behalf-of token per call.
Its replies are validated against the shared contracts like any other boundary."""

import asyncio
from collections.abc import Callable, Sequence

import httpx
from margin_copilot_shared.contracts import DraftRequest, Proposal, ProposalError
from margin_copilot_shared.security.context import current_request

from action_agent.application.drafts import DraftRejected

MAX_REPLY_BYTES = 64_000
REFUSALS = (403, 404, 409, 422)
Exchange = Callable[[str, Sequence[str]], str]


class ProposalsFailed(Exception):
    pass


class HttpProposals:
    def __init__(self, url: str, scope: str, exchange: Exchange, http: httpx.AsyncClient) -> None:
        self._url, self._scope, self._exchange, self._http = url, scope, exchange, http

    async def draft(self, request: DraftRequest) -> Proposal:
        token = await asyncio.to_thread(self._exchange, current_request().token, [self._scope])
        response = await self._http.post(
            f"{self._url}drafts",
            content=request.model_dump_json(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        body = response.content
        if len(body) > MAX_REPLY_BYTES:
            raise ProposalsFailed("reply too large")
        if response.status_code == 201:
            proposal = Proposal.model_validate_json(body)
            if proposal.status != "pending":  # the reply would say "pending"
                raise ProposalsFailed("a new draft must be pending")
            return proposal
        if response.status_code in REFUSALS:
            raise DraftRejected(response.status_code, ProposalError.model_validate_json(body))
        raise ProposalsFailed(f"proposals-api answered {response.status_code}")
