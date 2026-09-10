from __future__ import annotations

from pathlib import Path


def render_markdown(targets: list[dict], output: str = "out/research_gap_report.md") -> str:
    lines = ["# Research-gap internship targets", "", "Human review required before outreach.", ""]
    if not targets:
        lines += ["No candidates met the configured threshold in this run.", ""]
    for i, t in enumerate(targets, 1):
        lines += [
            f"## {i}. {t.get('author_name','Unknown researcher')}",
            f"**Researcher score:** {t.get('researcher_score', 0):.2f}",
            f"**Affiliations:** {', '.join(t.get('affiliations', [])) or 'unresolved'}",
            f"**Review status:** {t.get('review_status', 'pending')}",
            "",
        ]
        for p in t.get("papers", [])[:3]:
            lines += [
                f"### {p.get('title','Untitled')}",
                f"Paper score: {p.get('score', 0):.2f}",
                f"DOI: {p.get('doi') or 'none'}",
                f"Source provider: {p.get('source_provider') or 'metadata source'}",
                "",
            ]
            for g in (p.get("gaps") or [])[:3]:
                lines += [
                    f"**Gap type:** {g.get('gap_type', 'unknown')}",
                    f"**Capability mapped:** {g.get('capability', 'unknown')}",
                    f"**Evidence:** {g.get('evidence', '')}",
                    f"**Proposed bridge:** {g.get('bridge', '')}",
                    f"**Gap strength:** {g.get('gap_strength', 0):.2f} | **Capability:** {g.get('capability_strength', 0):.2f} | **Bridge:** {g.get('bridge_strength', 0):.2f}",
                    "",
                ]
        pitch = t.get("draft_pitch")
        email = t.get("draft_email")
        if pitch or email:
            lines += ["### Draft outreach", "", "**Executive pitch:**", "", pitch or "(not generated)", "", "**Email draft:**", "", "```text", email or "(not generated)", "```", ""]
        gmail_status = t.get("gmail_status")
        if gmail_status:
            lines += ["**Gmail draft status:** " + str(gmail_status)]
            if t.get("gmail_draft_id"):
                lines += [f"**Gmail draft ID:** {t.get('gmail_draft_id')}", f"**Gmail thread ID:** {t.get('gmail_thread_id') or 'n/a'}"]
            recipient = t.get("gmail_to") or t.get("public_email")
            if recipient:
                lines += [f"**Recipient:** {recipient}" + ("" if t.get("contact_verified") else " (agent-proposed — verify before sending)")]
            lines += [""]
        candidates = [c for c in (t.get("email_candidates") or []) if (c.get("email") or "").strip()]
        if candidates and not t.get("contact_verified"):
            lines += ["**Proposed recipients (verify before sending):**", ""]
            for c in candidates[:5]:
                lines += [f"- `{c['email']}` — source: {c.get('source', 'unknown')}{', ' + c['url'] if c.get('url') else ''}" + (" ✅ verified" if c.get("verified") else "")]
            lines += [""]
        lines += ["> Verify the original paper, exact limitation, author identity/affiliation, public institutional contact, and proposed experiment before outreach.", ""]
    text = "\n".join(lines)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(text, encoding="utf-8")
    return output
