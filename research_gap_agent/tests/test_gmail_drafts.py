import base64

from research_gap_agent import gmail_drafts as gd
from research_gap_agent.telegram import format_gmail_draft, format_run_summary


def _clear_env(monkeypatch):
    for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GMAIL_ENABLED", "GMAIL_SENDER"):
        monkeypatch.delenv(key, raising=False)


def test_disabled_without_credentials(monkeypatch):
    _clear_env(monkeypatch)
    assert gd.enabled() is False


def test_enabled_with_credentials(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh")
    assert gd.enabled() is True


def test_build_subject_truncates():
    assert len(gd.build_subject("x" * 500)) <= 240


def test_build_mime_roundtrip():
    raw = gd.build_mime("me", "prof@uni.edu", "Hello", "Body text")
    decoded = base64.urlsafe_b64decode(raw.encode()).decode("utf-8", "ignore")
    assert "prof@uni.edu" in decoded
    assert "Hello" in decoded


def _target(name="Ada Lovelace", verified=True, candidates=None):
    return {
        "author_name": name,
        "affiliations": ["Uni"],
        "paper_count": 1,
        "researcher_score": 90.0,
        "papers": [{"title": "Onion imaging", "doi": "10.1/x"}],
        "public_email": "ada@uni.edu" if verified else None,
        "contact_verified": verified,
        "contact_source": "paper_pdf_correspondence" if verified else None,
        "profile_url": "https://repo.testuni.edu/paper.pdf" if verified else None,
        "email_candidates": candidates or [],
        "draft_email": "Dear Dr. Lovelace, ...",
    }


def _creds(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "r")


def test_unverified_without_candidates_never_creates(monkeypatch):
    _creds(monkeypatch)
    out, created, errors = gd.create_drafts_for_targets([_target(verified=False)])
    assert created == 0 and errors == 0
    assert out[0]["gmail_status"] == "skipped_unverified"
    assert out[0]["gmail_draft_id"] is None
    assert out[0]["gmail_to"] is None


def test_unverified_with_candidates_creates_user_verify_draft(monkeypatch):
    _creds(monkeypatch)
    seen = {}
    def _fake_create(to, subject, body, cfg=None):
        seen.update(to=to, body=body)
        return {"gmail_draft_id": "d9", "gmail_thread_id": "t9", "gmail_message_id": "m9"}
    monkeypatch.setattr(gd, "create_draft", _fake_create)
    cands = [
        {"email": "a.lovelace@uni.edu", "url": "https://uni.edu/~ada", "source": "lab_website_contact", "verified": False},
        {"email": "ada@dept.uni.edu", "url": None, "source": "public_profile_page", "verified": False},
    ]
    out, created, errors = gd.create_drafts_for_targets([_target(verified=False, candidates=cands)])
    assert (created, errors) == (1, 0)
    assert out[0]["gmail_status"] == "created_unverified"
    assert out[0]["gmail_to"] == "a.lovelace@uni.edu"
    assert "VERIFY RECIPIENT" in seen["body"]
    assert "ada@dept.uni.edu" in seen["body"]
    assert "Dear Dr. Lovelace" in seen["body"]


def test_verified_draft_cites_source_not_verify_header(monkeypatch):
    _creds(monkeypatch)
    seen = {}
    monkeypatch.setattr(gd, "create_draft", lambda to, subject, body, cfg=None: seen.update(body=body) or {"gmail_draft_id": "d1", "gmail_thread_id": "t1", "gmail_message_id": "m1"})
    out, created, errors = gd.create_drafts_for_targets([_target(verified=True)])
    assert out[0]["gmail_status"] == "created"
    assert "VERIFY RECIPIENT" not in seen["body"]
    assert "Verified To: ada@uni.edu" in seen["body"]
    assert "https://repo.testuni.edu/paper.pdf" in seen["body"]


def test_verified_with_alternatives_lists_them_as_unverified(monkeypatch):
    _creds(monkeypatch)
    seen = {}
    monkeypatch.setattr(gd, "create_draft", lambda to, subject, body, cfg=None: seen.update(body=body) or {"gmail_draft_id": "d1", "gmail_thread_id": "t1", "gmail_message_id": "m1"})
    cands = [{"email": "a.other@lab.org", "url": "https://lab.org", "source": "lab_website_contact", "verified": False}]
    out, _, _ = gd.create_drafts_for_targets([_target(verified=True, candidates=cands)])
    assert out[0]["gmail_status"] == "created"
    assert "Verified To: ada@uni.edu" in seen["body"]
    assert "a.other@lab.org" in seen["body"]
    assert "VERIFY RECIPIENT" not in seen["body"]


def test_disabled_gmail_skips_verified(monkeypatch):
    _clear_env(monkeypatch)
    out, created, errors = gd.create_drafts_for_targets([_target(verified=True)])
    assert created == 0 and errors == 0
    assert out[0]["gmail_status"] == "skipped_disabled"


def test_verified_target_creates(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "r")
    monkeypatch.setattr(gd, "create_draft", lambda to, subject, body, cfg=None: {"gmail_draft_id": "d1", "gmail_thread_id": "t1", "gmail_message_id": "m1"})
    out, created, errors = gd.create_drafts_for_targets([_target(verified=True)])
    assert (created, errors) == (1, 0)
    assert out[0]["gmail_status"] == "created"
    assert out[0]["gmail_draft_id"] == "d1"


def test_api_error_recorded_not_raised(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "r")

    def _boom(to, subject, body, cfg=None):
        raise RuntimeError("quota")

    monkeypatch.setattr(gd, "create_draft", _boom)
    out, created, errors = gd.create_drafts_for_targets([_target(verified=True)])
    assert (created, errors) == (0, 1)
    assert out[0]["gmail_status"].startswith("error:")


def test_format_gmail_draft_created_shows_verified_source():
    text, markup = format_gmail_draft("Ada", "ada@uni.edu", "Subject", "d1", "t1", "created",
                                      verified_source="paper_pdf_correspondence — https://repo.testuni.edu/paper.pdf")
    assert "GMAIL DRAFT CREATED" in text
    assert "VERIFY RECIPIENT" not in text
    assert "https://repo.testuni.edu/paper.pdf" in text
    assert markup and "mail.google.com" in str(markup)


def test_format_gmail_draft_unverified_lists_alternatives():
    cands = [
        {"email": "a.lovelace@uni.edu", "url": "https://uni.edu/~ada", "source": "lab_website_contact", "verified": False},
        {"email": "ada@dept.uni.edu", "url": None, "source": "public_profile_page", "verified": False},
    ]
    text, markup = format_gmail_draft("Ada", "a.lovelace@uni.edu", "Subject", "d9", "t9", "created_unverified", cands)
    assert "VERIFY RECIPIENT" in text
    assert "ada@dept.uni.edu" in text
    assert markup and "mail.google.com" in str(markup)


def test_format_gmail_draft_skipped():
    text, markup = format_gmail_draft("Ada", "", "Subject", None, None, "skipped_unverified")
    assert "SKIPPED" in text
    assert markup is None


def test_run_summary_includes_gmail_counts():
    text = format_run_summary(10, 2, 1, gmail_drafts=2, gmail_errors=1)
    assert "Gmail drafts created: 2" in text
    assert "Gmail draft errors: 1" in text
