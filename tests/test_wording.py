from datetime import UTC, datetime
from decimal import Decimal

from margin_copilot_shared.contracts import Proposal

from action_agent.domain.wording import drafted


def proposal(**overrides):
    fields = {
        "id": "1a2b3c4d" + "0" * 24,
        "region": "N",
        "sku": "DAI-002",
        "product": "UHT milk 1 L",
        "tier": "B",
        "current_price": Decimal("7.00"),
        "new_price": Decimal("7.25"),
        "change_pct": Decimal("3.57"),
        "approver": "manager",
        "clause": "PP-04 §3.2",
        "status": "pending",
        "proposed_by": "oid-north",
        "proposed_at": datetime(2026, 11, 21, tzinfo=UTC),
    }
    return Proposal(**(fields | overrides))


def test_a_manager_level_draft_reads_exactly():
    assert drafted(proposal()) == (
        "Drafted proposal 1a2b3c4d, pending approval: UHT milk 1 L in the North, 7.00 → 7.25 MAD "
        "(+3.6%). The North pricing manager can approve it on the approval screen (PP-04 §3.2)."
    )


def test_a_director_level_draft_names_the_director():
    olive = proposal(
        region="C",
        product="Olive oil 1 L",
        current_price=Decimal("80.25"),
        new_price=Decimal("85.87"),
        change_pct=Decimal("7.00"),
        approver="director",
    )
    assert drafted(olive) == (
        "Drafted proposal 1a2b3c4d, pending approval: Olive oil 1 L in the Center, 80.25 → 85.87 "
        "MAD (+7.0%). Only the pricing director can approve it, on the approval screen "
        "(PP-04 §3.2)."
    )


def test_the_manager_sentence_never_says_director():
    for region in ("N", "C", "S"):
        assert "director" not in drafted(proposal(region=region)).lower()


def test_a_cut_shows_its_sign():
    cut = proposal(new_price=Decimal("6.86"), change_pct=Decimal("-2.00"), approver="director")
    assert "(-2.0%)" in drafted(cut)
