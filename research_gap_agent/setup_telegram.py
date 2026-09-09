from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN first.")
    req = Request(f"https://api.telegram.org/bot{token}/getUpdates", headers={"Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    found = {}
    for update in data.get("result", []):
        message = update.get("message") or update.get("edited_message") or update.get("channel_post")
        chat = (message or {}).get("chat") or {}
        if "id" in chat:
            found[str(chat["id"])] = chat.get("title") or chat.get("username") or chat.get("first_name") or "chat"
    if not found:
        raise SystemExit("No chat found. Open the bot in Telegram, press Start/send /start, then run this again.")
    print("Telegram chat IDs found:")
    for chat_id, label in found.items():
        print(f"{chat_id}\t{label}")


if __name__ == "__main__":
    main()
