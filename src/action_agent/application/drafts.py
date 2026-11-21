"""The action agent's one use case: the model extracts the request, proposals-api creates a
pending draft, and code words the reply. Agents can only draft; approval is a person's job."""

from decimal import Decimal, DecimalException
from typing import Literal, Protocol

from margin_copilot_shared.contracts import AgentReply, DraftRequest, Proposal, ProposalError
from margin_copilot_shared.security.context import current_request
from pydantic import BaseModel, ValidationError

from action_agent.domain import wording


class DraftIntent(BaseModel):
    """The model's structured output: what the user asked for, nothing decided."""

    is_draft: bool
    product: str
    region: Literal["N", "C", "S"] | None
    new_price: float | None
    change_pct: float | None


class DraftRejected(Exception):
    def __init__(self, status: int, error: ProposalError) -> None:
        super().__init__(f"{status}: {error.error}")
        self.status, self.error = status, error


class Extractor(Protocol):
    async def extract(self, question: str) -> DraftIntent: ...


class Proposals(Protocol):
    async def draft(self, request: DraftRequest) -> Proposal: ...


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _request(intent: DraftIntent) -> DraftRequest | None:
    try:
        if intent.new_price is not None:  # the model gave both: the price is the user's target
            return DraftRequest(
                product=intent.product, region=intent.region, new_price=_decimal(intent.new_price)
            )
        if intent.change_pct is not None:
            return DraftRequest(
                product=intent.product, region=intent.region, change_pct=_decimal(intent.change_pct)
            )
    except (ValidationError, DecimalException, ValueError, OverflowError):
        return None
    return None


async def draft_reply(question: str, extractor: Extractor, proposals: Proposals) -> AgentReply:
    intent = await extractor.extract(question)
    if not intent.is_draft:
        return AgentReply(answer=wording.NOT_A_DRAFT)
    request = _request(intent)
    if request is None:
        return AgentReply(answer=wording.NEED_A_CHANGE)
    try:
        proposal = await proposals.draft(request)
    except DraftRejected as rejected:
        return _refused(rejected, request)
    return AgentReply(answer=wording.drafted(proposal), citations=[proposal.clause])


def _refused(rejected: DraftRejected, request: DraftRequest) -> AgentReply:
    status, error = rejected.status, rejected.error
    if status == 403 and error.error == "region not allowed":
        return AgentReply(answer=wording.NOT_YOUR_REGION, refusal="no_access")
    if status == 403 and error.error == "no pricing role in your token":
        return AgentReply(answer=wording.NO_ROLE, refusal="no_access")
    if status == 404 and error.error == "no product matches":
        return AgentReply(answer=wording.NO_PRODUCT, refusal="no_data")
    if status == 404 and error.error == "no current price":
        return AgentReply(answer=wording.no_current_price(request.region), refusal="no_data")
    if status == 409 and error.error == "several products match" and error.matches:
        return AgentReply(answer=wording.which_one(error.matches))
    if status == 422:
        return AgentReply(answer=error.error, citations=[error.clause] if error.clause else [])
    # Not a draft outcome (a token-check 403 is a misconfiguration, not the user's permission):
    # the caller gets "action-agent failed".
    raise rejected


class Drafter:
    def __init__(self, extractor: Extractor, proposals: Proposals) -> None:
        self._extractor, self._proposals = extractor, proposals

    async def reply(self, question: str) -> AgentReply:
        return await draft_reply(question, self._extractor, self._proposals)


class FakeDrafter:
    async def reply(self, question: str) -> AgentReply:
        return AgentReply(answer=f"fake action-agent drafts as user {current_request().caller.oid}")
