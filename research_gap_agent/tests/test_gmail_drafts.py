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


def _target(name="Ada Lovelace", verified=True):
    return {
        "author_name": name,
        "affiliations": ["Uni"],
        "paper_count": 1,
        "researcher_score": 90.0,
        "papers": [{"title": "Onion imaging", "doi": "10.1/x"}],
        "public_email": "ada@uni.edu" if verified else None,
        "contact_verified": verified,
        "draft_email": "Dear Dr. Lovelace, ...",
    }


def test_unverified_targets_never_create(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "r")
    out, created, errors = gd.create_drafts_for_targets([_target(verified=False)])
    assert created == 0 and errors == 0
    assert out[0]["gmail_status"] == "skipped_unverified"
    assert out[0]["gmail_draft_id"] is None


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


def test_format_gmail_draft_created_has_link():
    text, markup = format_gmail_draft("Ada", "ada@uni.edu", "Subject", "d1", "t1", "created")
    assert "GMAIL DRAFT CREATED" in text
    assert "d1" in text
    assert markup and "mail.google.com" in str(markup)


def test_format_gmail_draft_skipped():
    text, markup = format_gmail_draft("Ada", "", "Subject", None, None, "skipped_unverified")
    assert "SKIPPED" in text
    assert markup is None


def test_run_summary_includes_gmail_counts():
    text = format_run_summary(10, 2, 1, gmail_drafts=2, gmail_errors=1)
    assert "Gmail drafts created: 2" in text
    assert "Gmail draft errors: 1" in text
