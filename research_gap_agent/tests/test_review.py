from research_gap_agent.review import approval_check, set_review_status


def test_pending_target_cannot_pass():
    ok, reasons = approval_check({"researcher_score": 91, "papers": [{"title": "x"}], "public_email": "a@uni.edu", "verification_url": "https://uni.edu/p", "review_status": "pending"})
    assert not ok
    assert "human approval missing" in reasons


def test_approved_verified_target_can_pass():
    ok, reasons = approval_check({"researcher_score": 91, "papers": [{"title": "x"}], "public_email": "a@uni.edu", "verification_url": "https://uni.edu/p", "review_status": "approved"})
    assert ok
    assert reasons == []


def test_invalid_status_rejected():
    try:
        set_review_status({}, "send")
    except ValueError:
        return
    raise AssertionError("invalid status must fail")
