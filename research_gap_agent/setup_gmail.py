from __future__ import annotations

import argparse
import json
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/gmail.compose"


def load_client(path: str) -> tuple[str, str, str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    section = data.get("web") or data.get("installed") or {}
    client_id = section.get("client_id", "")
    client_secret = section.get("client_secret", "")
    redirect_uris = section.get("redirect_uris") or []
    token_uri = section.get("token_uri") or "https://oauth2.googleapis.com/token"
    if not (client_id and client_secret and redirect_uris):
        raise SystemExit(f"Could not read client_id/client_secret/redirect_uris from {path}")
    return client_id, client_secret, redirect_uris[0], token_uri


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str, token_uri: str) -> dict:
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(token_uri, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def auth_url(client_id: str, redirect_uri: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    })


def loopback_flow(client_id: str, client_secret: str, redirect_uri: str, token_uri: str) -> str:
    parts = urllib.parse.urlparse(redirect_uri)
    if parts.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit(f"Loopback flow needs a localhost redirect URI, got: {redirect_uri}")
    port = parts.port or 80
    path = parts.path or "/"

    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.urlparse(self.path).query
            captured.update(urllib.parse.parse_qs(query))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if "code" in captured:
                self.wfile.write(b"<h1>Authorized - you can close this tab and return to the terminal.</h1>")
            else:
                self.wfile.write(b"<h1>Authorization failed or was denied. Return to the terminal.</h1>")

        def log_message(self, *args):  # keep output clean
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    url = auth_url(client_id, redirect_uri)
    print("Opening browser for Google consent (gmail.compose scope — drafts only) ...")
    print(url)
    webbrowser.open(url)
    thread.join(timeout=180)
    server.server_close()
    codes = captured.get("code")
    if not codes:
        err = captured.get("error", ["no code received (timeout or denied)"])
        raise SystemExit(f"Authorization failed: {err[0]}")
    token = exchange_code(codes[0], client_id, client_secret, redirect_uri, token_uri)
    if "refresh_token" not in token:
        raise SystemExit(f"No refresh_token returned: {token}. Remove the app's access at myaccount.google.com/permissions and retry.")
    return token["refresh_token"]


def main() -> None:
    p = argparse.ArgumentParser(description="One-time Google OAuth: get GOOGLE_REFRESH_TOKEN for Gmail drafts (creates drafts only, never sends).")
    p.add_argument("--client-json", default="", help="Path to Google Cloud OAuth client_secret JSON (kept outside the repo, never committed).")
    p.add_argument("--client-id", default="", help="Alternative to --client-json.")
    p.add_argument("--client-secret", default="", help="Alternative to --client-json.")
    p.add_argument("--redirect-uri", default="", help="Required with --client-id/--client-secret.")
    p.add_argument("--manual", action="store_true", help="Print the consent URL and paste the code instead of loopback.")
    args = p.parse_args()

    if args.client_json:
        client_id, client_secret, redirect_uri, token_uri = load_client(args.client_json)
    elif args.client_id and args.client_secret and args.redirect_uri:
        client_id, client_secret, redirect_uri = args.client_id, args.client_secret, args.redirect_uri
        token_uri = "https://oauth2.googleapis.com/token"
    else:
        raise SystemExit("Pass --client-json <path> (recommended) or --client-id/--client-secret/--redirect-uri.")

    if args.manual:
        print("1. Open this URL and authorize:")
        print(auth_url(client_id, redirect_uri))
        code = input("2. Paste the ?code= value here: ").strip()
        token = exchange_code(code, client_id, client_secret, redirect_uri, token_uri)
        if "refresh_token" not in token:
            raise SystemExit(f"No refresh_token returned: {token}")
        refresh = token["refresh_token"]
    else:
        refresh = loopback_flow(client_id, client_secret, redirect_uri, token_uri)

    print("\nStore this as the GOOGLE_REFRESH_TOKEN secret (GitHub Actions secret, never commit):")
    print(refresh)


if __name__ == "__main__":
    main()
