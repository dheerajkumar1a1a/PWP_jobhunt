from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import yaml

from .author_enrichment import enrich_author
from .draft_builder import build_email, build_pitch
from .fulltext import find_public_pdf, fetch_public_text, locate_gap_sentences
from .gap_engine import score_paper, to_dict
from .gmail_drafts import create_drafts_for_targets
from .openrouter_free import analyze_gap, draft_email as llm_draft_email
from .researchers import aggregate_researchers
from .review_report import render_markdown
from .scholarly import discover

DEFAULT_SCORING = {"minimum_target_score": 70.0, "priority_score": 80.0}


def abstract_text(work):
    inv = work.get("abstract_inverted_index") or {}
    words = [(p, token) for token, positions in inv.items() for p in positions]
    return " ".join(t for _, t in sorted(words))


def publish_metrics(scanned: int, targets: int, priority: int, errors: int, deep_count: int, verified_contacts: int, llm_count: int, gmail_drafts: int = 0, gmail_errors: int = 0):
    values = {"RG_SCANNED": scanned, "RG_CANDIDATES": targets, "RG_PRIORITY": priority, "RG_ERRORS": errors, "RG_DEEP_FULLTEXT": deep_count, "RG_VERIFIED_CONTACTS": verified_contacts, "RG_LLM_ANALYZED": llm_count, "RG_GMAIL_DRAFTS": gmail_drafts, "RG_GMAIL_ERRORS": gmail_errors}
    env_file = os.getenv("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")


def load_scoring(cfg: dict, config_path: str) -> dict:
    scoring = dict(DEFAULT_SCORING)
    scoring.update(cfg.get("scoring") or {})
    external = Path(config_path).with_name("scoring.yaml")
    if external.exists():
        try:
            external_data = yaml.safe_load(external.read_text(encoding="utf-8")) or {}
            thresholds = external_data.get("thresholds") or {}
            scoring.setdefault("minimum_target_score", float(thresholds.get("promising", 65)))
            scoring.setdefault("priority_score", float(thresholds.get("priority", 80)))
        except Exception as exc:
            print(f"Could not load external scoring.yaml: {exc}; using defaults")
    return scoring


def llm_project(cfg: dict) -> dict:
    return {
        "name": (cfg.get("project") or {}).get("name") or (cfg.get("project") or {}).get("title") or "research project",
        "objective": (cfg.get("project") or {}).get("objective", ""),
        "capabilities": (cfg.get("capabilities") or {}) or (cfg.get("project") or {}).get("capabilities", {}),
        "validation": (cfg.get("validation") or {}) or (cfg.get("project") or {}).get("evidence", {}),
    }


def deep_analyze_record(record: dict, work: dict, capabilities: dict[str, bool], cfg: dict) -> tuple[dict, bool]:
    initial = float(record.get("score", 0))
    if initial < 30:
        return record, False
    location = work.get("primary_location") or {}
    pdf_url = find_public_pdf(work.get("doi"), location)
    if not pdf_url:
        return record, False
    text = fetch_public_text(pdf_url)
    if not text:
        return {**record, "fulltext_url": pdf_url, "fulltext_status": "unreadable"}, False
    clipped = text[:120000]
    score, gaps = score_paper(record["title"], clipped, capabilities)
    evidence = locate_gap_sentences(clipped)
    gap_dicts = [to_dict(g) for g in gaps]
    updated = {**record, "score": max(initial, score), "gaps": gap_dicts or record.get("gaps", []), "fulltext_url": pdf_url, "fulltext_status": "analyzed", "fulltext_gap_sentences": evidence}
    llm = analyze_gap(llm_project(cfg), {"title": record["title"], "doi": record.get("doi"), "year": record.get("year"), "citations": record.get("citations", 0)}, "\n".join(evidence[:6]))
    if llm and not bool(llm.get("reject")) and float(llm.get("confidence", 0)) >= 0.60:
        updated["llm_gap_analysis"] = llm
        updated["gaps"] = [{
            "gap_type": "llm_assessed",
            "evidence": llm.get("gap_statement") or (evidence[0] if evidence else ""),
            "capability": llm.get("capability_match") or "",
            "bridge": llm.get("bridge") or "",
            "gap_strength": float(llm.get("evidence_strength", 0)),
            "capability_strength": float(llm.get("evidence_strength", 0)),
            "bridge_strength": float(llm.get("confidence", 0)),
            "score": round(max(initial, score) + 5.0 * float(llm.get("confidence", 0)), 2),
        }] + updated.get("gaps", [])
        updated["score"] = max(float(updated["score"]), max(initial, score))
        return updated, True
    return updated, False


def add_drafts_and_contacts(targets: list[dict], project_name: str, cfg: dict) -> tuple[list[dict], int, int]:
    out = []
    verified_count = 0
    llm_count = 0
    for t in targets:
        item = dict(t)
        merged: dict[str, dict] = {}
        for p in item.get("papers", []):
            for author in p.get("authors", []):
                name = (author.get("name") or "").strip()
                if name:
                    merged.setdefault(name, author)
        enriched = [enrich_author(a) for a in merged.values()]
        verified = [a for a in enriched if a.get("verified_public_institutional") and a.get("public_email")]
        item["authors_enriched"] = enriched
        item["public_email"] = verified[0].get("public_email") if verified else None
        item["verification_url"] = verified[0].get("profile_url") if verified else None
        item["contact_verified"] = bool(verified)
        verified_count += int(bool(verified))
        papers = list(item.get("papers", []))
        p = papers[0] if papers else {}
        gaps = p.get("gaps") or []
        g = gaps[0] if gaps else {}
        evidence = g.get("evidence") or "No paper-level gap evidence was extracted; manual verification is required."
        gap_type = g.get("gap_type", "methodological_constraint")
        capability = g.get("capability", "project capability")
        item["draft_pitch"] = build_pitch(item.get("author_name", "Researcher"), p.get("title", "Untitled"), evidence, gap_type, capability, project_name)
        item["draft_email"] = build_email(item.get("author_name", "Researcher"), p.get("title", "Untitled"), evidence, gap_type, capability, project_name)
        if os.getenv("OPENROUTER_API_KEY", "").strip() and os.getenv("OPENROUTER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
            llm_email = llm_draft_email(
                llm_project(cfg),
                {"name": item.get("author_name"), "affiliation": item.get("affiliations", []), "public_email": item.get("public_email")},
                p,
                g,
            )
            if llm_email:
                item["draft_email"] = llm_email.strip()
                llm_count += 1
        item["draft_review_status"] = "pending"
        out.append(item)
    return out, verified_count, llm_count


def scan(config_path: str, db_path: str = "data/research_gap.db", report_path: str = "out/research_gap_report.md"):
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    scoring = load_scoring(cfg, config_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, doi TEXT, title TEXT, year INTEGER, citations INTEGER, score REAL, gap_json TEXT, authors_json TEXT, raw_json TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS contacts(paper_id TEXT, author_name TEXT, affiliation TEXT, public_email TEXT, verification_url TEXT, review_status TEXT DEFAULT 'pending')")
    conn.execute("CREATE TABLE IF NOT EXISTS drafts(paper_id TEXT, author_name TEXT, pitch TEXT, email TEXT, review_status TEXT DEFAULT 'pending')")
    for _col in ("gmail_draft_id TEXT", "gmail_thread_id TEXT", "gmail_message_id TEXT", "gmail_status TEXT DEFAULT 'pending'", "gmail_subject TEXT"):
        _name = _col.split()[0]
        _existing = {r[1] for r in conn.execute("PRAGMA table_info(drafts)").fetchall()}
        if _name not in _existing:
            conn.execute(f"ALTER TABLE drafts ADD COLUMN {_col}")
    conn.execute("CREATE TABLE IF NOT EXISTS researcher_targets(author_name TEXT PRIMARY KEY, affiliations_json TEXT, paper_count INTEGER, researcher_score REAL, papers_json TEXT, review_status TEXT DEFAULT 'pending')")

    capabilities = {k: True for k, v in (cfg.get("capabilities") or {}).items() if v} or {k: True for k in (cfg.get("project") or {}).get("capabilities", [])}
    papers: list[dict] = []
    seen: set[str] = set()
    errors = 0
    search_cfg = cfg.get("search") or {}
    per_query = min(25, int(search_cfg.get("max_results_per_query", 25)))
    deep_limit = int(search_cfg.get("deep_fulltext_limit", 12))
    deep_count = 0
    llm_count = 0

    for q in search_cfg.get("seed_queries", []):
        try:
            works = discover(q, per_query)
        except Exception as exc:
            errors += 1
            print(f"Discovery failed for {q!r}: {exc}")
            continue
        if not works:
            errors += 1
            print(f"No scholarly results from configured providers for query {q!r}")
            continue
        for w in works:
            pid = (w.get("doi") or w.get("id") or w.get("title") or "").strip().lower()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            title = w.get("title") or "Untitled"
            abstract = abstract_text(w)
            score, gaps = score_paper(title, abstract, capabilities)
            authors = w.get("author_profiles") or [{"name": a.get("author", {}).get("display_name"), "institution": (a.get("institutions") or [{}])[0].get("display_name")} for a in w.get("authorships", [])]
            record = {"id": pid, "doi": w.get("doi"), "title": title, "score": score, "authors": authors, "gaps": [to_dict(g) for g in gaps], "source_provider": w.get("source_provider"), "year": w.get("publication_year"), "citations": w.get("cited_by_count", 0)}
            if deep_count < deep_limit and score >= 30:
                record, used_llm = deep_analyze_record(record, w, capabilities, cfg)
                deep_count += 1
                llm_count += int(used_llm)
            papers.append(record)
            conn.execute("INSERT OR REPLACE INTO papers VALUES (?,?,?,?,?,?,?,?,?)", (pid, w.get("doi"), title, w.get("publication_year"), w.get("cited_by_count", 0), record["score"], json.dumps(record["gaps"]), json.dumps(authors), json.dumps({**w, "fulltext_url": record.get("fulltext_url"), "fulltext_status": record.get("fulltext_status"), "llm_gap_analysis": record.get("llm_gap_analysis")})))

    min_score = float(scoring.get("minimum_target_score", 70))
    targets = aggregate_researchers(papers, min_score)[:int((cfg.get("outreach") or {}).get("max_candidates", 10))]
    targets, verified_contacts, llm_draft_count = add_drafts_and_contacts(targets, (cfg.get("project") or {}).get("name", "research project"), cfg)
    llm_count += llm_draft_count
    targets, gmail_created, gmail_errors = create_drafts_for_targets(targets)
    render_markdown(targets, report_path)

    for t in targets:
        conn.execute("INSERT OR REPLACE INTO researcher_targets VALUES (?,?,?,?,?,?)", (t["author_name"], json.dumps(t["affiliations"]), t["paper_count"], t["researcher_score"], json.dumps(t["papers"]), "pending"))
        primary = (t.get("papers") or [{}])[0]
        pid = primary.get("doi") or primary.get("title")
        conn.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?,?,?)", (pid, t["author_name"], t.get("draft_pitch", ""), t.get("draft_email", ""), "pending", t.get("gmail_draft_id"), t.get("gmail_thread_id"), t.get("gmail_message_id"), t.get("gmail_status", "pending"), t.get("gmail_subject", "")))
        for a in t.get("authors_enriched", []):
            conn.execute("INSERT INTO contacts VALUES (?,?,?,?,?,?)", (pid, a.get("name"), a.get("institution", ""), a.get("public_email"), a.get("profile_url"), "pending"))
    conn.commit(); conn.close()

    priority_cutoff = float(scoring.get("priority_score", 80))
    priority = sum(1 for t in targets if float(t["researcher_score"]) >= priority_cutoff)
    publish_metrics(len(seen), len(targets), priority, errors, deep_count, verified_contacts, llm_count, gmail_created, gmail_errors)
    print(f"Scanned {len(seen)} unique works; {len(targets)} researcher targets >= {min_score}. Priority: {priority}. Verified public contacts: {verified_contacts}. Query errors: {errors}. Deep full-text: {deep_count}. OpenRouter free LLM uses: {llm_count}. Gmail drafts: {gmail_created} created, {gmail_errors} errors. Report: {report_path}")


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
