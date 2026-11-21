"""draft_reply: the model only extracts; code drafts and words every reply."""

from decimal import Decimal

import pytest
from margin_copilot_shared.contracts import AgentReply, ProposalError

from action_agent.application.drafts import DraftRejected, draft_reply
from tests.fakes import FakeExtractor, FakeProposals
from tests.test_wording import proposal

QUESTION = "Draft a proposal to raise UHT milk 1 L in the North to 7.25 MAD."


async def reply(extractor, proposals):
    return await draft_reply(QUESTION, extractor, proposals)


def rejected(status, error, **fields):
    return DraftRejected(status, ProposalError(error=error, **fields))


async def test_a_request_that_isnt_a_draft_is_pointed_to_the_approval_screen():
    proposals = FakeProposals(proposal())
    answer = await reply(FakeExtractor(is_draft=False, new_price=7.25), proposals)
    assert answer == AgentReply(
        answer="I can only draft price-change proposals. Approving, rejecting and listing them "
        "happen on the approval screen."
    )
    assert proposals.requests == []


async def test_no_price_and_no_percent_asks_for_one():
    proposals = FakeProposals(proposal())
    answer = await reply(FakeExtractor(), proposals)
    assert answer == AgentReply(answer="Tell me the new price or the percentage change.")
    assert proposals.requests == []


async def test_a_draft_is_worded_from_the_stored_proposal():
    proposals = FakeProposals(proposal())
    answer = await reply(FakeExtractor(new_price=7.25, change_pct=3.6), proposals)
    assert answer.answer.startswith("Drafted proposal 1a2b3c4d, pending approval:")
    assert (answer.refusal, answer.citations) == (None, ["PP-04 §3.2"])
    request = proposals.requests[0]
    assert (request.product, request.region) == ("UHT milk 1 L", "N")
    assert (request.new_price, request.change_pct) == (Decimal("7.25"), None)


async def test_a_percent_goes_as_a_percent():
    proposals = FakeProposals(proposal())
    await reply(FakeExtractor(change_pct=-2.0), proposals)
    assert proposals.requests[0].change_pct == Decimal("-2.0")


async def test_another_region_is_no_access():
    answer = await reply(
        FakeExtractor(change_pct=2), FakeProposals(rejected(403, "region not allowed"))
    )
    assert answer == AgentReply(
        answer="You can draft proposals only for your own region.", refusal="no_access"
    )


async def test_an_unknown_product_is_no_data():
    answer = await reply(
        FakeExtractor(change_pct=2), FakeProposals(rejected(404, "no product matches"))
    )
    assert answer == AgentReply(answer="No product matches that name.", refusal="no_data")


async def test_no_current_price_is_no_data():
    failure = FakeProposals(rejected(404, "no current price"))
    answer = await reply(FakeExtractor(change_pct=2, region="S"), failure)
    assert answer == AgentReply(
        answer="No current price is recorded for that product in the South.", refusal="no_data"
    )


async def test_several_products_ask_which_one():
    matches = ["Fresh milk 1 L", "UHT milk 1 L"]
    failure = FakeProposals(rejected(409, "several products match", matches=matches))
    answer = await reply(FakeExtractor(product="milk", change_pct=2), failure)
    assert answer == AgentReply(
        answer="Several products match: Fresh milk 1 L, UHT milk 1 L. Which one?"
    )


async def test_a_refused_draft_carries_the_rule_and_its_clause():
    message = "PP-04 §3.1 caps Tier A increases at 3%; this would be +5.00%."
    failure = FakeProposals(rejected(422, message, clause="PP-04 §3.1"))
    answer = await reply(FakeExtractor(product="Fresh milk 1 L", change_pct=5), failure)
    assert answer == AgentReply(answer=message, citations=["PP-04 §3.1"])


async def test_values_the_contract_refuses_ask_again():
    answer = await reply(FakeExtractor(change_pct=500), FakeProposals(proposal()))
    assert answer == AgentReply(answer="Tell me the new price or the percentage change.")


@pytest.mark.parametrize("failure", [rejected(409, "already decided"), RuntimeError("boom")])
async def test_proposals_api_failure_raises(failure):
    with pytest.raises(Exception):  # noqa: B017 - any failure becomes "action-agent failed"
        await reply(FakeExtractor(change_pct=2), FakeProposals(failure))


async def test_no_pricing_role_says_so():
    failure = FakeProposals(rejected(403, "no pricing role in your token"))
    answer = await reply(FakeExtractor(change_pct=2), failure)
    assert answer == AgentReply(
        answer="Your sign-in doesn't show a pricing role, so you can't draft proposals. Ask an "
        "administrator.",
        refusal="no_access",
    )


@pytest.mark.parametrize("error", ["calling app not allowed", "missing scope"])
async def test_a_403_from_the_token_check_is_a_failure_not_a_refusal(error):
    with pytest.raises(DraftRejected):
        await reply(FakeExtractor(change_pct=2), FakeProposals(rejected(403, error)))
