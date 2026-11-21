"""Every reply about a draft is written here from the stored proposal, never by the model, so it
can't misstate the price, the percent, the status or who may approve (D-038)."""

from margin_copilot_shared.contracts import Proposal

REGION_NAMES = {"N": "North", "C": "Center", "S": "South"}
NOT_A_DRAFT = (
    "I can only draft price-change proposals. Approving, rejecting and listing them happen on the "
    "approval screen."
)
NEED_A_CHANGE = "Tell me the new price or the percentage change."
NOT_YOUR_REGION = "You can draft proposals only for your own region."
NO_PRODUCT = "No product matches that name."


def drafted(p: Proposal) -> str:
    region = REGION_NAMES[p.region]
    head = (
        f"Drafted proposal {p.id[:8]}, pending approval: {p.product} in the {region}, "
        f"{p.current_price} → {p.new_price} MAD ({p.change_pct:+.1f}%). "
    )
    if p.approver == "manager":  # never says "director", so a director-only case can't pass on it
        return (
            head
            + f"The {region} pricing manager can approve it on the approval screen ({p.clause})."
        )
    return head + f"Only the pricing director can approve it, on the approval screen ({p.clause})."


def no_current_price(region: str | None) -> str:
    where = f"the {REGION_NAMES[region]}" if region else "your region"
    return f"No current price is recorded for that product in {where}."


def which_one(matches: list[str]) -> str:
    return f"Several products match: {', '.join(matches)}. Which one?"
