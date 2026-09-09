from __future__ import annotations

from pathlib import Path


def render_markdown(targets: list[dict], output: str = "out/research_gap_report.md") -> str:
    lines = ["# Research-gap internship targets", "", "Human review required before outreach.", ""]
    for i, t in enumerate(targets, 1):
        lines += [
            f"## {i}. {t.get('author_name','Unknown researcher')}",
            f"**Researcher score:** {t.get('researcher_score', 0):.2f}",
            f"**Affiliations:** {', '.join(t.get('affiliations', [])) or 'unresolved'}",
            "",
        ]
        for p in t.get("papers", [])[:3]:
            lines += [f"- **{p.get('title','Untitled')}** — paper score {p.get('score', 0):.2f} — {p.get('doi') or 'no DOI'}"]
        lines += ["", "> Review the original paper, gap evidence, affiliation and public contact before use.", ""]
    text = "\n".join(lines)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(text, encoding="utf-8")
    return output
