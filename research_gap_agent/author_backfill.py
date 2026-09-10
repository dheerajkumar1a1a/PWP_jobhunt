from __future__ import annotations

from urllib.parse import quote

from . import scholarly

ORCID_API = "https://pub.orcid.org/v3.0"

# In-memory cache for the run: institution id -> homepage_url (or "").
_INST_HOMEPAGE_CACHE: dict[str, str] = {}


def _api_url(openalex_id: str) -> str:
    url = (openalex_id or "").strip()
    if url.startswith("https://openalex.org/"):
        return "https://api.openalex.org/" + url.rsplit("/", 1)[-1]
    return url


def _best_author_match(results: list[dict], name: str) -> dict | None:
    target = " ".join(name.lower().split())
    exact = [a for a in results if " ".join(((a.get("display_name") or "").lower().split())) == target]
    pool = exact or results
    return max(pool, key=lambda a: (a.get("works_count") or 0, a.get("cited_by_count") or 0), default=None)


def search_openalex_author(name: str) -> dict | None:
    """Find the most likely OpenAlex author record. Returns None on no confident match."""
    url = "https://api.openalex.org/authors?search=" + quote(name) + "&per-page=5"
    try:
        results = scholarly.get_json(url).get("results", [])
    except Exception as exc:
        print(f"openalex author search failed for {name!r}: {exc}")
        return None
    return _best_author_match(results, name)


def fetch_openalex_author(author_id: str) -> dict | None:
    """Exact author record by OpenAlex ID URL. No name-collision risk."""
    try:
        record = scholarly.get_json(_api_url(author_id))
    except Exception as exc:
        print(f"openalex author fetch failed for {author_id!r}: {exc}")
        return None
    return record if record and record.get("display_name") else None


def institution_homepage(institution_id: str) -> str:
    """Full institution object carries homepage_url; the dehydrated embedded
    record inside author responses does not."""
    if not institution_id:
        return ""
    key = _api_url(institution_id)
    if key in _INST_HOMEPAGE_CACHE:
        return _INST_HOMEPAGE_CACHE[key]
    try:
        homepage = scholarly.get_json(key).get("homepage_url") or ""
    except Exception:
        homepage = ""
    homepage = homepage if homepage.startswith(("http://", "https://")) else ""
    _INST_HOMEPAGE_CACHE[key] = homepage
    return homepage


def s2_author_homepage(author_id: str) -> str:
    """Semantic Scholar author records expose a homepage field."""
    if not author_id or str(author_id).startswith("http"):
        return ""
    try:
        data = scholarly.get_json(
            f"https://api.semanticscholar.org/graph/v1/author/{quote(str(author_id))}?fields=name,homepage",
            headers=scholarly._s2_headers(),
        )
    except Exception:
        return ""
    homepage = data.get("homepage") or ""
    return homepage if homepage.startswith(("http://", "https://")) else ""


def orcid_researcher_urls(orcid: str) -> list[str]:
    """Personal/lab page URLs from the public ORCID record. Empty on any failure."""
    oid = (orcid or "").rsplit("/", 1)[-1].strip()
    if not oid:
        return []
    try:
        data = scholarly.get_json(f"{ORCID_API}/{quote(oid)}/researcher-urls")
    except Exception:
        return []
    urls = []
    for entry in data.get("researcher-url", []) or []:
        value = (entry.get("url") or {}).get("value", "")
        if isinstance(value, str) and value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    return urls


def backfill_profile_urls(name: str, affiliation: str = "", author_id: str | None = None) -> tuple[list[str], str]:
    """Backfill verifiable profile URLs for authors that arrived with none.

    Chain: exact OpenAlex record (by ID) or author search → full institution
    homepage(s) → S2 author homepage → ORCID researcher-urls.
    Returns (urls, institution_name). Refuses name-search matches when a known
    affiliation contradicts them (wrong-person guard). Verification policy is
    unchanged: callers still run the strict institutional check on fetched pages.
    """
    match = fetch_openalex_author(author_id) if author_id and str(author_id).startswith("http") else None
    if match is None and name:
        match = search_openalex_author(name)
    if not match:
        s2_home = s2_author_homepage(author_id or "")
        return ([s2_home] if s2_home else []), ""
    institutions = match.get("last_known_institutions") or []
    inst_names = [i.get("display_name", "") for i in institutions if i.get("display_name")]
    if affiliation and inst_names and not any(
        affiliation.lower() in n.lower() or n.lower() in affiliation.lower() for n in inst_names
    ):
        return [], ""
    urls: list[str] = []
    for inst in institutions:
        homepage = institution_homepage(inst.get("id", ""))
        if homepage and homepage not in urls:
            urls.append(homepage)
    s2_home = s2_author_homepage(author_id or "")
    if s2_home and s2_home not in urls:
        urls.append(s2_home)
    orcid = (match.get("orcid") or "").strip()
    if orcid:
        for personal in orcid_researcher_urls(orcid):
            if personal not in urls:
                urls.append(personal)
        if orcid.startswith(("http://", "https://")) and orcid not in urls:
            urls.append(orcid)
    return urls, (inst_names[0] if inst_names else "")
