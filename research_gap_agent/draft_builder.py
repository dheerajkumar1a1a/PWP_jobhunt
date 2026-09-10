from __future__ import annotations

import re

APPLICANT_NAME = "Dheeraj Kumar"


def validate_draft(draft: str, author_name: str, applicant_name: str = APPLICANT_NAME) -> bool:
    """Safety gate for LLM-drafted outreach. Rejects identity confusion
    ("I am <recipient>") and drafts missing the applicant's signature."""
    if not (draft or "").strip():
        return False
    for token in (author_name or "").strip().split():
        if len(token) > 2 and re.search(rf"\bI am {re.escape(token)}\b", draft, re.I):
            return False
    return applicant_name.lower() in draft.lower()


def proposed_experiment(gap_type: str, capability: str) -> str:
    plans = {
        "destructive": "compare the non-destructive optical measurement against a reference biochemical assay on matched onion layers",
        "laboratory": "benchmark the portable optical workflow against the laboratory reference method using the same samples",
        "slow": "measure end-to-end analysis time and compare it with the current laboratory workflow",
        "manual": "evaluate automated segmentation and classification against expert-labelled samples",
        "expensive": "perform a cost/performance comparison between the proposed portable system and the reference instrument",
        "nonportable": "validate the method under field/near-field conditions while retaining controlled acquisition geometry",
    }
    return plans.get(gap_type, f"test the {capability} capability against the reported limitation using a matched validation experiment")


def _project_paragraph(capability: str, project_name: str, gap_type: str) -> str:
    capability = (capability or "").replace("_", " ").strip()
    experiment = proposed_experiment(gap_type, capability)
    return (
        f"My current project, '{project_name}', provides a {capability} capability that could be tested against this limitation. "
        f"A practical next experiment would be to {experiment}. "
        "The goal would be to generate a directly comparable validation dataset and determine whether the approach is strong enough to support a joint research direction."
    )


def build_pitch(author_name: str, paper_title: str, evidence: str, gap_type: str, capability: str, project_name: str) -> str:
    return (
        f"I studied your paper '{paper_title}' and focused on the reported issue: {evidence} "
        + _project_paragraph(capability, project_name, gap_type)
    )


def build_email(author_name: str, paper_title: str, evidence: str, gap_type: str, capability: str, project_name: str, applicant_profile: str = "") -> str:
    pitch = _project_paragraph(capability, project_name, gap_type)
    profile = applicant_profile.strip() or "I am seeking a research internship in which I can contribute an existing prototype and experimental validation work."
    last = author_name.split()[-1] if author_name.strip() else "Researcher"
    return (
        f"Dear Dr. {last},\n\n"
        f"I recently read your paper, '{paper_title}', and was particularly interested in this limitation: {evidence}\n\n"
        f"{pitch}\n\n"
        f"{profile}\n\n"
        "I would be grateful for the opportunity to discuss whether this could fit a short research internship under your supervision, with scope for a publishable experimental extension if the results are promising.\n\n"
        "Best regards,\nDheeraj Kumar"
    )
