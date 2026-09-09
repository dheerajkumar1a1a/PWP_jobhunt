from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from .gap_engine import score_paper, to_dict
from .researchers import aggregate_researchers
from .review_report import render_markdown

USER_AGENT = "research-gap-agent/0.4 (academic discovery; respectful rate; no automated outreach)"
TRANSIENT_HTTP = {429, 500, 502, 503, 504}


def get_json(url: str, retries: int = 5):
    last_error = None
    for attempt in range(retries):
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in TRANSIENT_HTTP or attempt == retries - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else min(30.0, 2.0 ** attempt)
            except ValueError:
                delay = min(30.0, 2.0 ** attempt)
            print(f"Transient HTTP {exc.code}; retrying in {delay:.1f}s ({attempt + 1}/{retries})")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            delay = min(30.0, 2.0 ** attempt)
            print(f"Network error; retrying in {delay:.1f}s ({attempt + 1}/{retries})")
            time.sleep(delay)
    raise last_error or RuntimeError("request failed")


def openalex_search(query: str, per_page: int = 25):
    url = "https://api.openalex.org/works?search=" + quote(query) + f"&per-page={per_page}&select=id,doi,title,publication_year,authorships,abstract_inverted_index,primary_location,cited_by_count"
    try:
        return get_json(url).get("results", [])
    except urllib.error.HTTPError as exc:
        print(f"OpenAlex failed for query {query!r}: HTTP {exc.code}; continuing to next query")
        return []


def abstract_text(work):
    inv = work.get("abstract_inverted_index") or {}
    words = [(p, token) for token, positions in inv.items() for p in positions]
    return " ".join(t for _, t in sorted(words))


def publish_metrics(scanned: int, targets: int, priority: int):
    values = {"RG_SCANNED": scanned, "RG_CANDIDATES": targets, "RG_PRIORITY": priority}
    env_file = os.getenv("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")


def scan(config_path: str, db_path: str = "data/research_gap.db", report_path: str = "out/research_gap_report.md"):
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, doi TEXT, title TEXT, year INTEGER, citations INTEGER, score REAL, gap_json TEXT, authors_json TEXT, raw_json TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS contacts(paper_id TEXT, author_name TEXT, affiliation TEXT, public_email TEXT, verification_url TEXT, review_status TEXT DEFAULT 'pending')")
    conn.execute("CREATE TABLE IF NOT EXISTS drafts(paper_id TEXT, author_name TEXT, pitch TEXT, email TEXT, review_status TEXT DEFAULT 'pending')")

    capabilities = {k: True for k in cfg["project"].get("capabilities", [])}
    papers: list[dict] = []
    seen: set[str] = set()
    errors = 0
    for q in cfg["search"]["seed_queries"]:
        try:
            works = openalex_search(q, min(100, int(cfg["search"].get("max_results_per_query", 25))))
        except Exception as exc:
            errors += 1
            print(f"Query failed: {q!r}: {exc}")
            continue
        for w in works:
            pid = w.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            title = w.get("title") or "Untitled"
            abstract = abstract_text(w)
            score, gaps = score_paper(title, abstract, capabilities)
            authors = [{"name": a.get("author", {}).get("display_name"), "institution": (a.get("institutions") or [{}])[0].get("display_name")} for a in w.get("authorships", [])]
            record = {"id": pid, "doi": w.get("doi"), "title": title, "score": score, "authors": authors, "gaps": [to_dict(g) for g in gaps]}
            papers.append(record)
            conn.execute("INSERT OR REPLACE INTO papers VALUES (?,?,?,?,?,?,?,?,?)", (pid, w.get("doi"), title, w.get("publication_year"), w.get("cited_by_count", 0), score, json.dumps(record["gaps"]), json.dumps(authors), json.dumps(w)))
        time.sleep(1.0)

    min_score = float(cfg["scoring"].get("minimum_target_score", 70))
    targets = aggregate_researchers(papers, min_score)[:int(cfg["outreach"].get("max_candidates", 10))]
    render_markdown(targets, report_path)
    conn.execute("CREATE TABLE IF NOT EXISTS researcher_targets(author_name TEXT PRIMARY KEY, affiliations_json TEXT, paper_count INTEGER, researcher_score REAL, papers_json TEXT, review_status TEXT DEFAULT 'pending')")
    for t in targets:
        conn.execute("INSERT OR REPLACE INTO researcher_targets VALUES (?,?,?,?,?,?)", (t["author_name"], json.dumps(t["affiliations"]), t["paper_count"], t["researcher_score"], json.dumps(t["papers"]), "pending"))
    conn.commit(); conn.close()

    priority_cutoff = float(cfg["scoring"].get("priority_score", 80))
    priority = sum(1 for t in targets if float(t["researcher_score"]) >= priority_cutoff)
    publish_metrics(len(seen), len(targets), priority)
    print(f"Scanned {len(seen)} unique works; {len(targets)} researcher targets >= {min_score}. Priority: {priority}. Query errors: {errors}. Report: {report_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Free-first research-gap discovery agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--config", required=True)
    s.add_argument("--db", default="data/research_gap.db")
    s.add_argument("--report", default="out/research_gap_report.md")
    a = p.parse_args()
    if a.cmd == "scan":
        scan(a.config, a.db, a.report)
