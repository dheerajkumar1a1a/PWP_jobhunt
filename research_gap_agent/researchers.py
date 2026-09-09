from __future__ import annotations

from collections import defaultdict


def aggregate_researchers(papers: list[dict], minimum_score: float = 70.0) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {"papers": [], "affiliations": set(), "max_score": 0.0})
    for paper in papers:
        score = float(paper.get("score", 0))
        if score < minimum_score:
            continue
        for author in paper.get("authors", []):
            name = (author.get("name") or "").strip()
            if not name:
                continue
            g = grouped[name]
            g["papers"].append({"title": paper.get("title"), "doi": paper.get("doi"), "score": score})
            if author.get("institution"):
                g["affiliations"].add(author["institution"])
            g["max_score"] = max(g["max_score"], score)

    targets = []
    for name, g in grouped.items():
        continuity = min(1.0, len(g["papers"]) / 3.0)
        score = round(min(100.0, g["max_score"] * 0.85 + 10 * continuity), 2)
        targets.append({
            "author_name": name,
            "affiliations": sorted(g["affiliations"]),
            "paper_count": len(g["papers"]),
            "papers": sorted(g["papers"], key=lambda x: x["score"], reverse=True),
            "researcher_score": score,
            "review_status": "pending",
        })
    return sorted(targets, key=lambda x: x["researcher_score"], reverse=True)
