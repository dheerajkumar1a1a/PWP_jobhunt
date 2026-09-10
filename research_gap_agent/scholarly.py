from __future__ import annotations

import json
import time
import urllib.error
from collections import defaultdict
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = "research-gap-agent/0.9 (academic discovery; respectful rate; no automated outreach)"
TRANSIENT = {429, 500, 502, 503, 504}


def get_json(url: str, retries: int = 3, headers: dict | None = None):
    last = None
    base = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        base.update(headers)
    for attempt in range(retries):
        req = Request(url, headers=base)
        try:
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in TRANSIENT or attempt == retries - 1:
                raise
            delay = min(12.0, float(exc.headers.get("Retry-After", 0) or (2 ** attempt)))
            time.sleep(delay)
    raise last or RuntimeError("request failed")


def _s2_headers() -> dict:
    import os
    key = os.getenv("S2_API_KEY", "").strip()
    return {"x-api-key": key} if key else {}


def _mailto() -> str:
    import os
    return os.getenv("SCHOLARLY_MAILTO", "").strip() or os.getenv("CROSSREF_MAILTO", "").strip()


def openalex_search(query: str, per_page: int = 100) -> list[dict]:
    """OpenAlex with cursor pagination (up to 200/page). Previously capped at 25 total."""
    per_page = max(1, min(per_page, 1000))
    out: list[dict] = []
    cursor = "*"
    mailto = _mailto()
    while len(out) < per_page:
        fetch = min(200, per_page - len(out))
        url = "https://api.openalex.org/works?search=" + quote(query) + f"&per-page={fetch}&cursor={quote(cursor, safe='')}&select=id,doi,title,publication_year,authorships,abstract_inverted_index,primary_location,cited_by_count"
        if mailto:
            url += "&mailto=" + quote(mailto)
        try:
            data = get_json(url)
        except Exception as exc:
            print(f"openalex failed for {query!r}: {exc}")
            break
        out.extend(data.get("results", []))
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    return out[:per_page]


def crossref_search(query: str, rows: int = 100) -> list[dict]:
    """Crossref with offset pagination (up to 1000/request). Previously capped at 10 total."""
    rows = max(1, min(rows, 1000))
    mailto = _mailto()
    items: list[dict] = []
    offset = 0
    while len(items) < rows:
        fetch = min(1000, rows - len(items))
        url = "https://api.crossref.org/works?query.bibliographic=" + quote(query) + f"&rows={fetch}&offset={offset}&select=DOI,title,published,author,URL,is-referenced-by-count,link"
        if mailto:
            url += "&mailto=" + quote(mailto)
        try:
            batch = get_json(url).get("message", {}).get("items", [])
        except Exception as exc:
            print(f"crossref failed for {query!r}: {exc}")
            break
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
    out = []
    for item in items:
        title = (item.get("title") or ["Untitled"])[0]
        authors = [{"author": {"display_name": f"{a.get('given','')} {a.get('family','')}".strip(), "id": None, "orcid": None}, "institutions": [{"display_name": (a.get("affiliation") or [{}])[0].get("name", "") if a.get("affiliation") else ""}]} for a in item.get("author", [])]
        out.append({
            "id": f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else item.get("URL"),
            "doi": f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None,
            "title": title,
            "publication_year": ((item.get("published") or {}).get("date-parts") or [[None]])[0][0],
            "authorships": authors,
            "abstract_inverted_index": {},
            "primary_location": {"landing_page_url": item.get("URL")},
            "cited_by_count": item.get("is-referenced-by-count", 0),
        })
    return out


def semantic_scholar_search(query: str, limit: int = 100) -> list[dict]:
    """Semantic Scholar with offset pagination (up to 100/request). Previously capped at 10 total."""
    limit = max(1, min(limit, 1000))
    headers = _s2_headers()
    raw: list[dict] = []
    offset = 0
    while len(raw) < limit:
        fetch = min(100, limit - len(raw))
        url = "https://api.semanticscholar.org/graph/v1/paper/search?query=" + quote(query) + "&limit=" + str(fetch) + "&offset=" + str(offset) + "&fields=paperId,title,abstract,year,authors,externalIds,openAccessPdf,citationCount"
        try:
            batch = get_json(url, headers=headers).get("data", [])
        except Exception as exc:
            print(f"semantic_scholar failed for {query!r}: {exc}")
            break
        if not batch:
            break
        raw.extend(batch)
        offset += len(batch)
    items = raw[:limit]
    out = []
    for item in items:
        authors = [{"author": {"display_name": a.get("name"), "id": a.get("authorId"), "orcid": None}, "institutions": []} for a in item.get("authors", [])]
        abstract = item.get("abstract") or ""
        positions = defaultdict(list)
        for i, word in enumerate(abstract.split()):
            positions[word].append(i)
        out.append({
            "id": "s2:" + str(item.get("paperId")),
            "doi": ((item.get("externalIds") or {}).get("DOI")),
            "title": item.get("title") or "Untitled",
            "publication_year": item.get("year"),
            "authorships": authors,
            "abstract_inverted_index": dict(positions),
            "primary_location": {"pdf": {"url": ((item.get("openAccessPdf") or {}).get("url"))}},
            "cited_by_count": item.get("citationCount", 0),
        })
    return out


def _enrich_openalex_authors(authorships: list[dict]) -> list[dict]:
    out = []
    for a in authorships or []:
        author = a.get("author") or {}
        profile = dict(author)
        institutions = a.get("institutions") or []
        profile_record = {
            "name": profile.get("display_name"),
            "author_id": profile.get("id"),
            "orcid": profile.get("orcid"),
            "profile_url": profile.get("id"),
            "institution": (institutions[0].get("display_name") if institutions else ""),
        }
        out.append(profile_record)
    return out


def discover(query: str, per_query: int = 100) -> list[dict]:
    """Return deduplicated works from several free scholarly sources."""
    works: list[dict] = []
    seen: set[str] = set()
    providers = [
        ("openalex", lambda: openalex_search(query, per_query)),
        ("crossref", lambda: crossref_search(query, per_query)),
        ("semantic_scholar", lambda: semantic_scholar_search(query, per_query)),
    ]
    for provider, fn in providers:
        try:
            results = fn()
        except Exception as exc:
            print(f"{provider} failed for {query!r}: {exc}")
            results = []
        for w in results:
            key = (w.get("doi") or w.get("id") or w.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            w["source_provider"] = provider
            if provider == "openalex":
                w["author_profiles"] = _enrich_openalex_authors(w.get("authorships", []))
            else:
                w["author_profiles"] = [
                    {"name": (a.get("author") or {}).get("display_name"), "author_id": (a.get("author") or {}).get("id"), "orcid": (a.get("author") or {}).get("orcid"), "profile_url": None, "institution": (a.get("institutions") or [{}])[0].get("display_name", "")}
                    for a in w.get("authorships", [])
                ]
            works.append(w)
        time.sleep(1.0)
    return works
