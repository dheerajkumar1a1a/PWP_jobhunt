from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    enabled: bool = True


def from_env() -> TelegramConfig:
    return TelegramConfig(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        enabled=os.getenv("TELEGRAM_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
    )


def send_message(text: str, cfg: TelegramConfig | None = None, timeout: int = 20, reply_markup: dict | None = None) -> bool:
    cfg = cfg or from_env()
    if not cfg.enabled or not cfg.bot_token or not cfg.chat_id:
        return False
    url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    fields = {"chat_id": cfg.chat_id, "text": text, "disable_web_page_preview": "true"}
    if reply_markup:
        fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    payload = urlencode(fields).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False


def format_candidate(name: str, affiliation: str, paper: str, score: float, gap: str) -> str:
    return (
        "🔬 RESEARCH-GAP CANDIDATE\n\n"
        f"{name}\n{affiliation}\n\n"
        f"Fit score: {score:.1f}/100\nPaper: {paper}\n\n"
        f"Why it matches:\n{gap[:1600]}\n\n"
        "📧 Copy-ready email is below. Review the paper/gap before sending."
    )


def format_email_draft(author_name: str, subject: str, body: str) -> tuple[str, dict]:
    safe_subject = subject.strip()[:240]
    safe_body = body.strip()
    gmail_url = "https://mail.google.com/mail/?" + urlencode({
        "view": "cm",
        "fs": "1",
        "su": safe_subject,
        "body": safe_body,
    })
    message = (
        "📧 COPY-READY EMAIL\n\n"
        f"To: {author_name.strip() or 'Researcher'}\n"
        f"Subject: {safe_subject}\n\n"
        "──────── EMAIL BODY ────────\n"
        f"{safe_body}\n"
        "──────── END EMAIL ─────────\n\n"
        "Review the source paper, gap evidence, and recipient before sending."
    )
    markup = {"inline_keyboard": [[
        {"text": "📋 Copy Subject", "copy_text": {"text": safe_subject}},
        {"text": "✉️ Open Gmail Compose", "url": gmail_url},
    ]]}
    return message, markup


def format_run_summary(scanned: int, accepted: int, priority: int, errors: int = 0, deep_fulltext: int = 0, verified_contacts: int = 0, gmail_drafts: int = 0, gmail_errors: int = 0) -> str:
    lines = [
        "📚 RESEARCH-GAP SCAN COMPLETE",
        "",
        f"Papers scanned: {scanned}\nCandidates: {accepted}\nPriority targets: {priority}",
        f"Deep full-text analyzed: {deep_fulltext}\nVerified public contacts: {verified_contacts}\nErrors: {errors}",
        f"Gmail drafts created: {gmail_drafts}\nGmail draft errors: {gmail_errors}",
        "",
        "Candidate + copy-ready outreach drafts follow.",
    ]
    return "\n".join(lines)


def format_gmail_draft(author_name: str, to_email: str, subject: str, draft_id: str | None, thread_id: str | None, status: str, candidates: list[dict] | None = None) -> tuple[str, dict | None]:
    """Full draft tracking alert. Returns (message, reply_markup or None)."""
    from .gmail_drafts import draft_gmail_link

    if status in ("created", "created_unverified") and draft_id:
        link = draft_gmail_link(thread_id)
        if status == "created_unverified":
            alts = [c for c in (candidates or []) if (c.get("email") or "").strip() and c.get("email") != to_email][:4]
            lines = [
                "✉️ GMAIL DRAFT CREATED — VERIFY RECIPIENT\n",
                f"To (agent-proposed, NOT verified): {author_name.strip() or 'Researcher'} <{to_email}>",
                f"Subject: {subject.strip()[:240]}",
                f"Gmail draft ID: {draft_id}\n",
            ]
            for c in alts:
                lines.append(f"Also found: {c['email']} (source: {c.get('source', 'unknown')}{', ' + c['url'] if c.get('url') else ''})")
            lines += [
                "",
                "Open the draft, confirm the To field against the source link(s), fix it if needed, then Send. Nothing was auto-sent.",
            ]
            markup: dict | None = {"inline_keyboard": [[{"text": "📝 Open Gmail Draft & Verify", "url": link}]]}
            return "\n".join(lines), markup
        message = (
            "✉️ GMAIL DRAFT CREATED\n\n"
            f"To: {author_name.strip() or 'Researcher'} <{to_email}>\n"
            f"Subject: {subject.strip()[:240]}\n"
            f"Gmail draft ID: {draft_id}\n\n"
            "Draft is in your Gmail Drafts — review and press Send yourself. Nothing was auto-sent.\n"
            "Verify the paper, gap evidence, and recipient before sending."
        )
        markup = {"inline_keyboard": [[{"text": "📝 Open Gmail Draft", "url": link}]]}
        return message, markup
    reason = {
        "skipped_unverified": "no verified public institutional email — SQLite draft only.",
        "skipped_disabled": "Gmail disabled/missing GOOGLE_* credentials — SQLite draft only.",
    }.get(status, status)
    message = (
        "✉️ GMAIL DRAFT SKIPPED\n\n"
        f"To: {author_name.strip() or 'Researcher'} <{to_email or 'no email'}>\n"
        f"Subject: {subject.strip()[:240]}\n"
        f"Status: {reason}\n\n"
        "Copy-ready email draft is still in the report/previous message."
    )
    return message, None
