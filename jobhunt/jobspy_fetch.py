"""JobSpy adapter for the personalized jobhunt pipeline.

The adapter keeps JobSpy isolated from the rest of the agent and normalizes
its DataFrame rows into the existing Job dataclass. It intentionally uses the
Python JobSpy site list supported by the upstream package; Naukri is not
silently treated as a supported Python scraper.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from .fetch import Job, strip_html


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _salary(row: dict[str, Any]) -> str | None:
    direct = _clean(row.get("salary"))
    if direct:
        return direct
    minimum = _clean(row.get("min_amount"))
    maximum = _clean(row.get("max_amount"))
    currency = _clean(row.get("currency"))
    period = _clean(row.get("interval"))
    if minimum or maximum:
        values = " - ".join(v for v in (minimum, maximum) if v)
        bits = " ".join(v for v in (currency, values, period) if v)
        return bits or None
    return None


def _location(row: dict[str, Any]) -> str:
    explicit = _clean(row.get("location"))
    if explicit:
        return explicit
    bits = [_clean(row.get(k)) for k in ("city", "state", "country")]
    return ", ".join(dict.fromkeys(x for x in bits if x))


def _posted_at(row: dict[str, Any]) -> str | None:
    value = row.get("date_posted") or row.get("posted_at")
    cleaned = _clean(value)
    return cleaned or None


def _stable_id(row: dict[str, Any], site: str, url: str) -> str:
    raw = "|".join([
        site,
        _clean(row.get("job_id") or row.get("id")),
        _clean(row.get("company")),
        _clean(row.get("title")),
        url,
    ])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"jobspy:{site}:{digest}"


def _build_job(row: dict[str, Any]) -> Job:
    site = _clean(row.get("site") or "jobspy").lower()
    title = _clean(row.get("title"))
    company = _clean(row.get("company") or row.get("company_name"))
    location = _location(row)
    url = _clean(row.get("job_url") or row.get("url"))
    raw_description = _clean(row.get("description"))
    description = strip_html(raw_description) or raw_description
    return Job(
        job_id=_stable_id(row, site, url),
        ats=site,
        company=company or "Unknown",
        title=title,
        location=location,
        url=url,
        description=description,
        posted_at=_posted_at(row),
        salary=_salary(row),
    )


def fetch_jobspy(config: dict[str, Any]) -> list[Job]:
    """Run configured JobSpy searches and normalize the returned rows."""
    if not config.get("enabled", True):
        return []

    try:
        from jobspy import scrape_jobs
    except ImportError as exc:
        raise RuntimeError(
            "python-jobspy is not installed. Install requirements.txt first."
        ) from exc

    sites = list(config.get("sites") or [
        "linkedin", "indeed", "glassdoor", "google",
        "zip_recruiter", "bayt", "bdjobs",
    ])
    search_terms = list(config.get("search_terms") or ["data analyst"])
    locations = list(config.get("locations") or ["India"])
    results_wanted = int(config.get("results_wanted", 10))
    hours_old = config.get("hours_old")
    country_indeed = _clean(config.get("country_indeed") or "India")
    distance = int(config.get("distance", 50))
    is_remote = bool(config.get("is_remote", True))
    job_type = config.get("job_type", "fulltime")
    proxies = config.get("proxies")
    linkedin_fetch_description = bool(config.get("linkedin_fetch_description", True))
    sleep_seconds = float(config.get("sleep_seconds", 0.5))

    jobs: list[Job] = []
    seen_urls: set[str] = set()

    for term in search_terms:
        for location in locations:
            kwargs: dict[str, Any] = {
                "site_name": sites,
                "search_term": term,
                "location": location,
                "results_wanted": results_wanted,
                "country_indeed": country_indeed,
                "distance": distance,
                "is_remote": is_remote,
            }
            if hours_old is not None:
                kwargs["hours_old"] = int(hours_old)
            if job_type:
                kwargs["job_type"] = job_type
            if proxies:
                kwargs["proxies"] = proxies
            if linkedin_fetch_description:
                kwargs["linkedin_fetch_description"] = True
            if "google" in sites:
                kwargs["google_search_term"] = f"{term} jobs near {location}"

            try:
                frame = scrape_jobs(**kwargs)
            except Exception as exc:
                print(
                    f"  ! JobSpy query failed for {term!r} / {location!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if frame is None:
                continue

            for row in frame.to_dict("records"):
                job = _build_job(row)
                key = job.url or job.job_id
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                jobs.append(job)
            time.sleep(sleep_seconds)

    return jobs
