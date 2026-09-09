from __future__ import annotations

VALID = {"pending", "approved", "rejected"}


def set_review_status(record: dict, status: str) -> dict:
    status = status.strip().lower()
    if status not in VALID:
        raise ValueError(f"invalid review status: {status}")
    updated = dict(record)
    updated["review_status"] = status
    return updated


def approval_check(record: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if float(record.get("researcher_score", 0)) < 70:
        reasons.append("score below 70")
    if not record.get("papers"):
        reasons.append("no linked papers")
    if not record.get("public_email"):
        reasons.append("public institutional email not verified")
    if not record.get("verification_url"):
        reasons.append("contact verification source missing")
    if record.get("review_status") != "approved":
        reasons.append("human approval missing")
    return (not reasons, reasons)
