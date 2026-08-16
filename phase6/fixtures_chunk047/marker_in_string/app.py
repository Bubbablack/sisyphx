"""Module docstring that happens to mention REVIEW: as ordinary prose,
not an actionable inline marker."""


def build_message(status: str) -> str:
    # This is legitimate string content, not a review marker.
    return f"Ticket status: {status}. Needs REVIEW: before merge."


TEMPLATE = "Please add a REVIEW: note if you have concerns."
