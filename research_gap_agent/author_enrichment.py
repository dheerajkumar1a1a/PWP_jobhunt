from __future__ import annotations

import re
import time
from urllib.parse import quote, urljoin, urlparse

from . import scholarly
from .author_backfill import backfill_profile_urls, fetch_openalex_author, institution_homepage, search_openalex_author
from .enrichment import fetch_text, find_named_institutional_email, resolve_public_profile, to_dict
from .fulltext import extract_corresponding_email, fetch_public_text

# Cap on PDF fetches per author: the fallback serves at most ~10 candidates,
# so worst case is a few dozen polite requests per scan.
OA_PDF_FETCH_CAP = 6
# One-hop lab-site crawl budget per author (start pages + contact/people sub-pages).
LAB_CRAWL_FETCH_CAP = 8
CONTACT_SLUG_HINTS = (
    "contact", "contacts", "contact-us", "people", "team", "members", "member",
    "staff", "group", "about", "persons", "personnel", "kontakt", "equipe",
)
HREF_RE = re.compile(r"""href=["']([^"'#>]+)["']""", re.I)


def _resolve_author_match(name: str, author_id: str | None = None) -> dict | None:
    if author_id and str(author_id).startswith("http"):
        try:
            match = fetch_openalex_author(str(author_id))
        except Exception:
            match = None
        if match:
            return match
    if name:
        try:
            return search_openalex_author(name)
        except Exception:
            return None
    return None


def _institution_domains(match: dict | None) -> set[str]:
    domains: set[str] = set()
    for inst in ((match or {}).get("last_known_institutions") or []):
        host = (urlparse(institution_homepage(inst.get("id", ""))).hostname or "").lower()
        if host:
            domains.add(host[4:] if host.startswith("www.") else host)
    return domains


def _oa_pdf_urls(author_id: str) -> list[tuple[str, str]]:
    """(title, pdf_url) across all locations of the author's works, repository copies first."""
    aid = author_id.rsplit("/", 1)[-1]
    url = ("https://api.openalex.org/works?filter=author.id:" + aid
           + "&per-page=25&select=title,locations")
    try:
        works = scholarly.get_json(url).get("results", [])
    except Exception:
        return []
    publisher, repository = [], []
    for work in works:
        title = work.get("title") or ""
        for loc in work.get("locations", []) or []:
            pdf = loc.get("pdf_url")
            if not pdf or not pdf.startswith(("http://", "https://")):
                continue
            host = (urlparse(pdf).hostname or "").lower()
            entry = (title, pdf)
            if any(p in host for p in ("sciencedirect", "springer", "wiley", "acs.org", "tandfonline", "rsc.org", "nature.com", "oup.com")):
                publisher.append(entry)
            else:
                repository.append(entry)
    return repository + publisher


def correspondence_from_oa_works(name: str, author_id: str | None = None, affiliation: str = "") -> dict | None:
    """Last-resort contact: the author's own correspondence email printed in one
    of their open-access papers. Only returned when the email domain matches a
    homepage domain of the author's OpenAlex institution — same strict bar as
    profile verification, different source. Returns None on any doubt."""
    try:
        match = _resolve_author_match(name, author_id)
        domains = _institution_domains(match)
        if not domains or not (match or {}).get("id"):
            return None
        for title, pdf_url in _oa_pdf_urls(match["id"])[:OA_PDF_FETCH_CAP]:
            try:
                text = fetch_public_text(pdf_url)
            except Exception:
                continue
            finally:
                time.sleep(1.0)
            email = extract_corresponding_email(text, name)
            if email and email.rsplit("@", 1)[-1].lower() in domains:
                return {
                    "name": name,
                    "institution": affiliation or (match.get("last_known_institutions") or [{}])[0].get("display_name", ""),
                    "profile_url": pdf_url,
                    "public_email": email,
                    "contact_source": "paper_pdf_correspondence",
                    "verified_public_institutional": True,
                    "profile_backfilled": False,
                    "correspondence_paper": title,
                }
    except Exception:
        return None
    return None


def _http_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def lab_contact_crawl(name: str, start_urls: list[str] | None, author_id: str | None = None, affiliation: str = "") -> dict | None:
    """Follow Contact/People links one hop from the author's own stated sites
    (ORCID researcher-urls, homepages). Same host only; the email must still
    name the person on an institutional domain. Returns None on any doubt."""
    try:
        match = _resolve_author_match(name, author_id)
        domains = _institution_domains(match)
        if not domains:
            return None
        institution = affiliation or ((match or {}).get("last_known_institutions") or [{}])[0].get("display_name", "")
        queue = [(u, 0) for u in (start_urls or []) if _http_url(u)]
        seen: set[str] = set()
        fetches = 0
        while queue and fetches < LAB_CRAWL_FETCH_CAP:
            url, depth = queue.pop(0)
            key = url.split("#")[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            try:
                html = fetch_text(url)
            except Exception:
                continue
            finally:
                time.sleep(1.0)
            fetches += 1
            email = find_named_institutional_email(html, name, domains)
            if email:
                return {
                    "name": name,
                    "institution": institution,
                    "profile_url": url,
                    "public_email": email,
                    "contact_source": "lab_website_contact",
                    "verified_public_institutional": True,
                    "profile_backfilled": False,
                }
            if depth > 0:
                continue
            base = (urlparse(url).hostname or "").lower()
            for href in HREF_RE.findall(html or ""):
                full = urljoin(url, href)
                if not _http_url(full):
                    continue
                host = (urlparse(full).hostname or "").lower()
                if host != base and not host.endswith("." + base):
                    continue
                if any(hint in full.lower() for hint in CONTACT_SLUG_HINTS):
                    queue.append((full, 1))
    except Exception:
        return None
    return None


def europepmc_affiliation_email(name: str, orcid: str | None = None, author_id: str | None = None, affiliation: str = "") -> dict | None:
    """PubMed-indexed affiliation strings sometimes carry the author's address
    ('Electronic address: x@y.edu'). ORCID-queried, name- and domain-checked."""
    if not orcid:
        return None
    try:
        match = _resolve_author_match(name, author_id)
        domains = _institution_domains(match)
        if not domains:
            return None
        url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=ORCID:%22"
               + quote(str(orcid), safe="") + "%22&format=json&pageSize=10&resultType=core")
        results = ((scholarly.get_json(url).get("resultList") or {}).get("result") or [])
        for res in results:
            email = find_named_institutional_email(res.get("affiliation") or "", name, domains)
            if email:
                source, pmid = (res.get("source") or "MED"), (res.get("id") or "")
                return {
                    "name": name,
                    "institution": affiliation or ((match or {}).get("last_known_institutions") or [{}])[0].get("display_name", ""),
                    "profile_url": f"https://europepmc.org/article/{source}/{pmid}" if pmid else None,
                    "public_email": email,
                    "contact_source": "europepmc_affiliation",
                    "verified_public_institutional": True,
                    "profile_backfilled": False,
                }
    except Exception:
        return None
    return None


def candidate_profile_urls(author: dict) -> list[str]:
    urls = []
    for key in ("profile_url", "orcid", "homepage"):
        value = author.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            urls.append(value)
    return urls


def enrich_author(author: dict) -> dict:
    name = (author.get("name") or "").strip()
    affiliation = (author.get("institution") or "").strip()
    urls = candidate_profile_urls(author)
    backfilled = False
    if not urls and name:
        urls, backfilled_institution = backfill_profile_urls(name, affiliation, author.get("author_id"))
        backfilled = bool(urls)
        if not affiliation and backfilled_institution:
            affiliation = backfilled_institution
    profile = resolve_public_profile(name, affiliation, urls)
    lab_hit = None
    if not profile.verified_public_institutional and urls and name:
        lab_hit = lab_contact_crawl(name, urls, author.get("author_id"), affiliation)
    result = dict(author)
    if not (result.get("institution") or "").strip() and affiliation:
        result["institution"] = affiliation
    if lab_hit:
        result.update({
            "profile_url": lab_hit["profile_url"],
            "public_email": lab_hit["public_email"],
            "contact_source": lab_hit["contact_source"],
            "verified_public_institutional": True,
            "profile_backfilled": backfilled,
        })
        return result
    result.update({
        "profile_url": profile.profile_url,
        "public_email": profile.email,
        "contact_source": profile.source,
        "verified_public_institutional": profile.verified_public_institutional,
        "profile_backfilled": backfilled,
    })
    return result
