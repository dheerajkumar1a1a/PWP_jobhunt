from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"


def enabled() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip()) and os.getenv("OPENROUTER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def chat(system: str, user: str, model: str = DEFAULT_MODEL, temperature: float = 0.1, max_tokens: int = 1200) -> str | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or not enabled():
        return None
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = Request(BASE_URL, data=payload, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dheerajkumar1a1a/PWP_jobhunt",
        "X-Title": "Research Gap Internship Agent",
    }, method="POST")
    try:
        with urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
    except Exception as exc:
        print(f"OpenRouter free-model request failed: {exc}")
        return None


def analyze_gap(project: dict, paper: dict, evidence: str) -> dict | None:
    system = (
        "You are a conservative academic research-gap analyst. Do not invent facts. "
        "Use only the supplied project and paper evidence. Return JSON with keys: "
        "gap_statement, evidence_strength, capability_match, bridge, novelty_rationale, "
        "confidence, reject. confidence is 0-1. reject is true when the match is weak or speculative."
    )
    user = json.dumps({"project": project, "paper": paper, "evidence": evidence}, ensure_ascii=False)
    text = chat(system, user, max_tokens=900)
    if not text:
        return None
    try:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    except Exception as exc:
        print(f"OpenRouter JSON parse failed: {exc}")
    return None


def draft_email(project: dict, researcher: dict, paper: dict, gap: dict) -> str | None:
    system = (
        "You write concise, professional academic internship outreach. Use only supplied facts. "
        "Never claim a paper says something unless present in evidence. Mention one specific gap, "
        "one concrete experiment, the applicant's demonstrated project capability, and ask for a "
        "short research internship/conversation. Return only the email body."
    )
    user = json.dumps({"project": project, "researcher": researcher, "paper": paper, "gap": gap}, ensure_ascii=False)
    return chat(system, user, max_tokens=900)
