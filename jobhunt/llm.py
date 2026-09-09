"""Two-stage LLM layer: cheap screen over everything, rich draft for the top few.

Cost lives here, so the two stages are deliberately lopsided:
  screen  batch jobs per call, short JD, cheaper model
  draft   one call per shortlisted job, longer JD, stronger model
"""
from __future__ import annotations

import json
import re
from typing import Any

from .fetch import Job
from .providers import LLMError, Provider, resolve

_FENCE_OPEN = re.compile(r"^\s*```(?:json|JSON)?\s*", re.M)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.M)

DRAFT_KEYS = ("fit_summary", "tailored_bullets", "gaps", "cover_note", "questions_to_ask")
SCREEN_MAX_TOKENS = 4000
DRAFT_MAX_TOKENS = 8000
PROFILE_MAX_TOKENS = 4000


def parse_json(raw: str) -> Any:
    """Parse model JSON, tolerating fences and short preambles."""
    if raw is None:
        raise ValueError("empty model reply")
    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", raw)).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    candidates = []
    for opener, closer in (("[", "]"), ("{", "}")):
        i, k = cleaned.find(opener), cleaned.rfind(closer)
        if i != -1 and k > i:
            candidates.append((i, cleaned[i:k + 1]))
    for _, blob in sorted(candidates):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"could not parse JSON from model reply: {cleaned[:300]!r}")


def _as_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("jobs", "results", "scores", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
        return [payload]
    raise ValueError(f"expected a JSON array of results, got {type(payload).__name__}")


PROFILE_PROMPT = """Extract a structured job-search profile from this resume.

Return ONLY a JSON object, no prose, no markdown fences:
{
  "name": str,
  "current_title": str,
  "years_experience": number | null,
  "core_skills": [str],
  "domains": [str],
  "notable_projects": [str],
  "education": str,
  "target_titles": [str],
  "seniority": str
}

Use null or an empty string when the resume does not establish a fact. Never
invent years of experience, education or seniority."""


def build_profile(resume_bytes: bytes | None = None, resume_text: str | None = None,
                  is_pdf: bool = False, provider: Provider | None = None,
                  model: str | None = None) -> dict:
    if provider is None or model is None:
        provider, model = resolve("draft")

    if is_pdf and resume_bytes:
        try:
            raw = provider.complete_document(
                model, PROFILE_PROMPT, resume_bytes, PROFILE_MAX_TOKENS)
        except LLMError as e:
            raise LLMError(
                f"{e}\nTip: export your resume to .txt and re-run, or set "
                f"DRAFT_PROVIDER=anthropic|gemini for PDF support."
            ) from e
    else:
        raw = provider.complete(
            model, "", f"{PROFILE_PROMPT}\n\n--- RESUME ---\n{resume_text or ''}",
            PROFILE_MAX_TOKENS, json_mode=True)

    profile = parse_json(raw)
    if not isinstance(profile, dict):
        raise ValueError("profile extraction did not return a JSON object")
    return profile


SCREEN_SYSTEM = """You screen job postings for one candidate. You are strict.

Score 0-10 on genuine fit:
  9-10  strong match and realistic next-step role
  7-8   good match, worth applying
  5-6   plausible but meaningful gaps
  0-4   wrong role family, clear hard requirement miss, or severe seniority mismatch

Important:
- Treat a null/unknown profile field as UNKNOWN, not as a missing qualification.
- Do not penalize the candidate for unknown years of experience, education or seniority.
- Do penalize a posting that explicitly requires information the candidate clearly lacks.
- Senior/staff/lead/manager roles remain low-fit unless the profile establishes that level.
- Internships are low-fit unless the profile explicitly targets internships.
- Penalize country/work-authorization constraints when they are explicit and incompatible.

Do not inflate scores to be encouraging. Most postings are a 4.

Return ONLY a JSON array, one object per job, no prose:
[{"job_id": str, "score": number, "reason": str}]
Echo `job_id` back exactly. `reason` is one sentence, max 20 words, concrete about the deciding factor."""


def screen(jobs: list[Job], profile: dict, batch_size: int = 8, jd_chars: int = 1800,
           provider: Provider | None = None, model: str | None = None) -> list[Job]:
    if provider is None or model is None:
        provider, model = resolve("screen")
    batch_size = max(1, int(batch_size))
    profile_blob = json.dumps(profile, ensure_ascii=False)

    for start in range(0, len(jobs), batch_size):
        batch = jobs[start:start + batch_size]
        payload = [{
            "job_id": j.job_id,
            "company": j.company,
            "title": j.title,
            "location": j.location,
            "description": j.description[:jd_chars],
        } for j in batch]

        n = start // batch_size + 1
        try:
            raw = provider.complete(
                model, SCREEN_SYSTEM,
                f"CANDIDATE PROFILE:\n{profile_blob}\n\n"
                f"JOBS:\n{json.dumps(payload, ensure_ascii=False)}",
                SCREEN_MAX_TOKENS, json_mode=True,
            )
            results = {}
            for r in _as_list(parse_json(raw)):
                jid = r.get("job_id")
                if jid:
                    results[str(jid)] = r
        except (LLMError, ValueError, KeyError, TypeError) as e:
            print(f"  ! screen batch {n} failed ({type(e).__name__}: {e}) — skipping")
            continue

        for j in batch:
            r = results.get(j.job_id)
            if not r:
                continue
            try:
                j.score = max(0.0, min(10.0, float(r.get("score", 0))))
            except (TypeError, ValueError):
                j.score = 0.0
            j.reason = str(r.get("reason", "")).strip()

        print(f"  screened {min(start + batch_size, len(jobs))}/{len(jobs)}")

    return jobs


DRAFT_SYSTEM = """You prepare an application kit for one job.

Hard rule: never invent experience. Every claim must trace to something in the
candidate profile. If the profile does not support a claim, it goes in `gaps`.

Return ONLY a JSON object:
{
  "fit_summary": str,
  "tailored_bullets": [str],
  "gaps": [str],
  "cover_note": str,
  "questions_to_ask": [str]
}"""


def draft(jobs: list[Job], profile: dict, jd_chars: int = 6000,
          provider: Provider | None = None, model: str | None = None) -> list[Job]:
    if provider is None or model is None:
        provider, model = resolve("draft")
    profile_blob = json.dumps(profile, ensure_ascii=False)

    for j in jobs:
        try:
            raw = provider.complete(
                model, DRAFT_SYSTEM,
                f"CANDIDATE PROFILE:\n{profile_blob}\n\n"
                f"JOB: {j.title} at {j.company} ({j.location or 'location not stated'})\n"
                f"URL: {j.url}\n\n{j.description[:jd_chars]}",
                DRAFT_MAX_TOKENS, json_mode=True,
            )
            kit = parse_json(raw)
            if not isinstance(kit, dict):
                raise ValueError("draft did not return a JSON object")
            j.draft = {
                "fit_summary": str(kit.get("fit_summary") or ""),
                "tailored_bullets": [str(b) for b in (kit.get("tailored_bullets") or [])],
                "gaps": [str(g) for g in (kit.get("gaps") or [])],
                "cover_note": str(kit.get("cover_note") or ""),
                "questions_to_ask": [str(q) for q in (kit.get("questions_to_ask") or [])],
            }
            print(f"  drafted {j.title} @ {j.company}")
        except (LLMError, ValueError, KeyError, TypeError) as e:
            print(f"  ! draft failed for {j.job_id} ({type(e).__name__}: {e})")
            j.draft = {k: ("" if k in ("fit_summary", "cover_note") else []) for k in DRAFT_KEYS}

    return jobs


def keyword_screen(jobs: list[Job], profile: dict, **_) -> list[Job]:
    """DEV ONLY. Token-overlap stand-in; never use for real matching."""
    skills = {s.lower() for s in profile.get("core_skills", []) if s}
    titles = [t.lower() for t in profile.get("target_titles", []) if t]
    for j in jobs:
        blob = f"{j.title} {j.description}".lower()
        hits = sorted(s for s in skills if s in blob)
        overlap = len(hits) / max(len(skills), 1)
        title_bonus = 2.5 if any(t in j.title.lower() for t in titles) else 0.0
        j.score = round(min(10.0, overlap * 12 + title_bonus), 1)
        j.reason = ("[keyword stub] matched: " + ", ".join(hits[:5])) if hits \
            else "[keyword stub] no skill overlap"
    return jobs
