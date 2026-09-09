from __future__ import annotations

import json
import time
import urllib.error
from collections import defaultdict
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = "research-gap-agent/0.9 (academic discovery; respectful rate; no automated outreach)"
TRANSIENT = {429, 500, 502, 503, 504}


def get_json(url: str, retries: int = 3):
    last = None
    for attempt in range(retries):
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
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


def openalex_search(query: str, per_page: int = 25) -> list[dict]:
    url = "https://api.openalex.org/works?search=" + quote(query) + f"&per-page={min(per_page,25)}&select=id,doi,title,publication_year,authorships,abstract_inverted_index,primary_location,cited_by_count"
    return get_json(url).get("results", [])


def crossref_search(query: str, rows: int = 10) -> list[dict]:
    url = "https://api.crossref.org/works?query.bibliographic=" + quote(query) + f"&rows={min(rows,10)}&select=DOI,title,published,author,URL,is-referenced-by-count,link"
    items = get_json(url).get("message", {}).get("items", [])
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


def semantic_scholar_search(query: str, limit: int = 10) -> list[dict]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search?query=" + quote(query) + "&limit=" + str(min(limit,10)) + "&fields=paperId,title,abstract,year,authors,externalIds,openAccessPdf,citationCount"
    try:
        items = get_json(url).get("data", [])
    except Exception as exc:
        print(f"semantic_scholar failed for {query!r}: {exc}")
        return []
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


def discover(query: str, per_query: int = 25) -> list[dict]:
    """Return deduplicated works from several free scholarly sources."""
    works: list[dict] = []
    seen: set[str] = set()
    providers = [
        ("openalex", lambda: openalex_search(query, per_query)),
        ("crossref", lambda: crossref_search(query, min(10, per_query))),
        ("semantic_scholar", lambda: semantic_scholar_search(query, min(10, per_query))),
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
