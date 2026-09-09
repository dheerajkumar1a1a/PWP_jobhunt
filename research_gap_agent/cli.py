from __future__ import annotations
import argparse, json, sqlite3, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import yaml

USER_AGENT = "research-gap-agent/0.1 (academic discovery; contact repository owner before high-volume use)"


def get_json(url: str):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def openalex_search(query: str, per_page: int = 25):
    url = "https://api.openalex.org/works?search=" + quote(query) + f"&per-page={per_page}&select=id,doi,title,publication_year,authorships,abstract_inverted_index,primary_location,cited_by_count"
    return get_json(url).get("results", [])


def abstract_text(work):
    inv = work.get("abstract_inverted_index") or {}
    words = []
    for token, positions in inv.items():
        for p in positions:
            words.append((p, token))
    return " ".join(t for _, t in sorted(words))


def evidence_score(text: str):
    t = text.lower()
    gap_terms = ["limitation", "limited", "challenge", "difficult", "cannot", "future work", "need to", "remain", "requires", "laborious", "expensive", "destructive"]
    capability_terms = ["smartphone", "portable", "non-destructive", "colorimetry", "cielab", "computer vision", "segmentation", "rapid", "low-cost"]
    return min(1.0, sum(x in t for x in gap_terms) / 4), min(1.0, sum(x in t for x in capability_terms) / 4)


def scan(config_path: str, db_path: str = "research_gap.db"):
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, doi TEXT, title TEXT, year INTEGER, citations INTEGER, gap_evidence REAL, capability_match REAL, score REAL, authors_json TEXT, raw_json TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS contacts(paper_id TEXT, author_name TEXT, affiliation TEXT, public_email TEXT, verification_url TEXT, review_status TEXT DEFAULT 'pending')")
    conn.execute("CREATE TABLE IF NOT EXISTS drafts(paper_id TEXT, author_name TEXT, pitch TEXT, email TEXT, review_status TEXT DEFAULT 'pending')")
    seen = set()
    for q in cfg["search"]["seed_queries"]:
        for w in openalex_search(q):
            pid = w.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            text = (w.get("title") or "") + " " + abstract_text(w)
            gap, match = evidence_score(text)
            # Base score is intentionally conservative; deeper full-text analysis is a later stage.
            score = round(30*gap + 25*match, 2)
            authors = [{"name": a.get("author", {}).get("display_name"), "institution": (a.get("institutions") or [{}])[0].get("display_name")} for a in w.get("authorships", [])]
            conn.execute("INSERT OR REPLACE INTO papers VALUES (?,?,?,?,?,?,?,?,?,?)", (pid, w.get("doi"), w.get("title"), w.get("publication_year"), w.get("cited_by_count",0), gap, match, score, json.dumps(authors), json.dumps(w)))
        time.sleep(0.2)
    conn.commit(); conn.close()
    print(f"Scanned {len(seen)} unique works. Results: {db_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--config", required=True)
    s.add_argument("--db", default="research_gap.db")
    a = p.parse_args()
    if a.cmd == "scan":
        scan(a.config, a.db)
