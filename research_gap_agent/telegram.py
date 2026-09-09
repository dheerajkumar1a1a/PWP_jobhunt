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
        f"🔬 RESEARCH-GAP CANDIDATE\n\n{name}\n{affiliation}\n\n"
        f"Fit score: {score:.1f}/100\nPaper: {paper}\n\n"
        f"Why it matches:\n{gap[:1200]}\n\n"
        "📧 A copy-ready email draft follows. Review the paper/gap before sending."
    )


def format_email_draft(author_name: str, subject: str, body: str) -> tuple[str, dict]:
    message = (
        "📧 COPY-READY EMAIL\n\n"
        f"To: {author_name.strip() or 'Researcher'}\n"
        f"Subject: {subject}\n\n"
        "──────── EMAIL BODY ────────\n"
        f"{body}\n"
        "──────── END EMAIL ─────────\n\n"
        "Telegram lets you long-press/select this message and Copy the full text for pasting into Gmail."
    )
    markup = {"inline_keyboard": [[{"text": "📋 Copy Subject", "copy_text": {"text": subject[:256]}}]]}
    return message, markup


def format_run_summary(scanned: int, accepted: int, priority: int, errors: int = 0, deep_fulltext: int = 0, verified_contacts: int = 0) -> str:
    return (
        "📚 RESEARCH-GAP SCAN COMPLETE\n\n"
        f"Papers scanned: {scanned}\nCandidates: {accepted}\nPriority targets: {priority}\n"
        f"Deep full-text analyzed: {deep_fulltext}\nVerified public contacts: {verified_contacts}\nErrors: {errors}\n\n"
        "Check the candidate messages below for copy-ready outreach drafts."
    )
