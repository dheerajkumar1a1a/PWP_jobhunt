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


def send_message(text: str, cfg: TelegramConfig | None = None, timeout: int = 20) -> bool:
    cfg = cfg or from_env()
    if not cfg.enabled or not cfg.bot_token or not cfg.chat_id:
        return False
    url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    payload = urlencode({"chat_id": cfg.chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False


def format_candidate(name: str, affiliation: str, paper: str, score: float, gap: str) -> str:
    return (f"🔬 Research-gap candidate\n\n{name}\n{affiliation}\n\n"
            f"Score: {score:.1f}/100\nPaper: {paper}\n\nGap evidence:\n{gap[:900]}\n\n"
            "Action: review in GitHub; do not auto-send outreach.")


def format_run_summary(scanned: int, accepted: int, priority: int, errors: int = 0) -> str:
    return ("📚 Research-gap scan complete\n\n"
            f"Papers scanned: {scanned}\nCandidates: {accepted}\nPriority targets: {priority}\nErrors: {errors}\n\n"
            "Open the GitHub artifact/report for review.")
