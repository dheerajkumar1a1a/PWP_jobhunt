from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from email.mime.text import MIMEText

GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


@dataclass(frozen=True)
class GmailConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    sender: str = "me"
    enabled: bool = True


def from_env() -> GmailConfig:
    return GmailConfig(
        client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN", "").strip(),
        sender=os.getenv("GMAIL_SENDER", "me").strip() or "me",
        enabled=os.getenv("GMAIL_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
    )


def enabled(cfg: GmailConfig | None = None) -> bool:
    cfg = cfg or from_env()
    return bool(cfg.enabled and cfg.client_id and cfg.client_secret and cfg.refresh_token)


def build_subject(paper_title: str) -> str:
    base = f"Research internship proposal inspired by {paper_title or 'your work'}"
    return base.strip()[:240]


def build_mime(sender: str, to: str, subject: str, body: str) -> str:
    msg = MIMEText(body.strip(), "plain", "utf-8")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject.strip()[:240]
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")


def _service(cfg: GmailConfig):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("google-api-python-client/google-auth not installed") from exc
    creds = Credentials(
        token=None,
        refresh_token=cfg.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        scopes=[GMAIL_COMPOSE_SCOPE],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def create_draft(to: str, subject: str, body: str, cfg: GmailConfig | None = None) -> dict:
    """Create a Gmail draft via drafts.create. Never sends. Returns id/threadId/message id.

    Raises RuntimeError when disabled/misconfigured, or propagates API errors
    to the caller (caller records gmail_status='error: ...').
    """
    cfg = cfg or from_env()
    if not enabled(cfg):
        raise RuntimeError("Gmail drafts disabled or GOOGLE_* credentials missing")
    if not (to or "").strip():
        raise ValueError("recipient email required for Gmail draft")
    service = _service(cfg)
    raw = build_mime(cfg.sender if cfg.sender != "me" else "me", to.strip(), subject, body)
    created = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    message = created.get("message") or {}
    return {
        "gmail_draft_id": created.get("id"),
        "gmail_thread_id": message.get("threadId"),
        "gmail_message_id": message.get("id"),
    }


def draft_gmail_link(thread_id: str | None) -> str:
    if thread_id:
        return f"https://mail.google.com/mail/u/0/#drafts/{thread_id}"
    return "https://mail.google.com/mail/u/0/#drafts"


def build_verify_header(top: dict, rest: list[dict]) -> str:
    """Human-verification checklist prepended to user-review drafts.

    The agent proposes; the user confirms the To field when opening the
    draft. Nothing here is a verified contact."""
    lines = [
        "[VERIFY RECIPIENT — agent-proposed, NOT verified]",
        f"To: {top['email']}  (source: {top.get('source', 'unknown')}{', ' + top['url'] if top.get('url') else ''})",
    ]
    for c in rest[:4]:
        lines.append(f"Also found: {c['email']}  (source: {c.get('source', 'unknown')}{', ' + c['url'] if c.get('url') else ''})")
    lines += [
        "Checklist before Send: 1) open the source link, 2) confirm the name and address match, 3) fix the To field if needed.",
        "---",
    ]
    return "\n".join(lines)


def create_drafts_for_targets(targets: list[dict], cfg: GmailConfig | None = None) -> tuple[list[dict], int, int]:
    """Verified-contacts-only Gmail draft creation, plus user-review drafts.

    Only targets with contact_verified + public_email get a `created` draft.
    Targets with agent-proposed email_candidates get a `created_unverified`
    draft addressed to the top candidate, with a verification header baked
    into the body — the user confirms the recipient when opening the draft.
    Nothing is ever sent. Others keep gmail_status='skipped_unverified'.
    When Gmail is disabled, all targets get gmail_status='skipped_disabled'.
    """
    cfg = cfg or from_env()
    out: list[dict] = []
    created = 0
    errors = 0
    gmail_on = enabled(cfg)
    for t in targets:
        item = dict(t)
        papers = list(item.get("papers") or [{}])
        paper = papers[0] if papers else {}
        subject = build_subject(paper.get("title", ""))
        item["gmail_subject"] = subject
        to_email = (item.get("public_email") or "").strip()
        candidates = [c for c in (item.get("email_candidates") or []) if (c.get("email") or "").strip()]
        if not (item.get("contact_verified") and to_email):
            if not candidates:
                item["gmail_status"] = "skipped_unverified"
                item["gmail_draft_id"] = None
                item["gmail_thread_id"] = None
                item["gmail_to"] = None
                out.append(item)
                continue
            to_email = candidates[0]["email"]
            item["gmail_status"] = "created_unverified"
        else:
            item["gmail_status"] = "created"
        item["gmail_to"] = to_email
        if not gmail_on:
            item["gmail_status"] = "skipped_disabled"
            item["gmail_draft_id"] = None
            item["gmail_thread_id"] = None
            out.append(item)
            continue
        try:
            body = item.get("draft_email", "")
            if item["gmail_status"] == "created_unverified":
                body = build_verify_header(candidates[0], candidates[1:]) + "\n\n" + (body or "")
            result = create_draft(to_email, subject, body, cfg)
            item["gmail_draft_id"] = result.get("gmail_draft_id")
            item["gmail_thread_id"] = result.get("gmail_thread_id")
            item["gmail_message_id"] = result.get("gmail_message_id")
            created += 1
        except Exception as exc:
            item["gmail_draft_id"] = None
            item["gmail_thread_id"] = None
            item["gmail_status"] = f"error: {exc}"
            errors += 1
        out.append(item)
    return out, created, errors
