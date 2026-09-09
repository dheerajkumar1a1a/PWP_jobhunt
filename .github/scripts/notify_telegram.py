"""Telegram notifier for the jobhunt digest. Stdlib only.

Reads out/tracker.csv, picks today's unsent-kb candidates (score >= threshold,
or top-N by score), sends a short HTML summary via sendMessage and the full
digest via sendDocument.

Env: TELEGRAM_BOT_TOKEN (required), TELEGRAM_CHAT_ID (required).
Usage: python .github/scripts/notify_telegram.py [--top 5] [--threshold 7.0] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import html
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TRACKER = ROOT / "out" / "tracker.csv"
DIGEST = ROOT / "out" / "digest.html"


def api(method: str, token: str, payload: dict) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/" + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        import json
        return json.load(r)


def send_document(token: str, chat_id: str, path: Path, caption: str) -> dict:
    import json as _json
    boundary = "----jobhunt boundary"
    body = b""
    body += ("--" + boundary + "\r\n"
             'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
             + chat_id + "\r\n").encode()
    body += ("--" + boundary + "\r\n"
             'Content-Disposition: form-data; name="caption"\r\n\r\n'
             + caption + "\r\n").encode()
    blob = path.read_bytes()
    body += ("--" + boundary + "\r\n"
             'Content-Disposition: form-data; name="document"; filename="'
             + path.name + '"\r\n'
             "Content-Type: text/html\r\n\r\n").encode() + blob + b"\r\n"
    body += ("--" + boundary + "--\r\n").encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendDocument", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return _json.load(r)


def load_candidates(top: int, threshold: float) -> list[dict]:
    if not TRACKER.exists():
        return []
    rows = list(csv.DictReader(TRACKER.read_text(encoding="utf-8").splitlines()))
    today = date.today().isoformat()
    fresh = [r for r in rows if (r.get("first_seen") or "")[:10] == today
             and (r.get("applied") or "").lower() != "true"]
    scored = []
    for r in fresh:
        try:
            score = float(r.get("score") or "nan")
        except ValueError:
            continue
        if score == score:  # not NaN
            scored.append((score, r))
    scored.sort(key=lambda p: p[0], reverse=True)
    picked = [r for (s, r) in scored if s >= threshold][:top]
    if not picked:
        picked = [r for (s, r) in scored][:top]
    return picked


def fmt_row(r: dict) -> str:
    score = r.get("score") or "?"
    title = html.escape(r.get("title") or "?")
    company = html.escape(r.get("company") or "?")
    loc = html.escape(r.get("location") or "?")
    reason = html.escape((r.get("reason") or "")[:160])
    url = html.escape(r.get("url") or "", quote=True)
    line = "<b>" + title + "</b> @ " + company + " (" + score + ")\n" + loc
    if reason:
        line += "\n<i>" + reason + "</i>"
    if url:
        line += '\n<a href="' + url + '"> posting</a>'
    return line


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=7.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
        return 1

    picks = load_candidates(args.top, args.threshold)
    if picks:
        text = "<b>Morning digest: " + str(len(picks)) + " worth a look</b>\n\n" \
            + "\n\n".join(fmt_row(r) for r in picks)
    else:
        text = "Morning digest: nothing new cleared the bar today. Full tables in the artifact."

    if args.dry_run:
        print(text)
        print("(dry-run: not sent)")
        return 0

    res = api("sendMessage", token,
              {"chat_id": chat_id, "text": text[:4000],
               "parse_mode": "HTML", "disable_web_page_preview": True})
    print("message sent, id:", res.get("result", {}).get("message_id"))
    if DIGEST.exists():
        res2 = send_document(token, chat_id, DIGEST, "Full digest (HTML)")
        print("document sent, id:", res2.get("result", {}).get("message_id"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
