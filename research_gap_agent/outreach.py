from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearcherTarget:
    author_name: str
    paper_title: str
    gap_evidence: str
    capability: str
    proposed_experiment: str
    affiliation: str
    score: float


def make_pitch(t: ResearcherTarget) -> str:
    return (
        f"Your work on '{t.paper_title}' highlights an important constraint: {t.gap_evidence} "
        f"I have developed a low-cost, non-destructive smartphone optical system whose demonstrated capability includes {t.capability}. "
        f"A focused next step would be to {t.proposed_experiment} This could turn the methodological limitation into a directly testable research question."
    )


def make_email(t: ResearcherTarget, applicant_profile: str) -> str:
    pitch = make_pitch(t)
    return (
        f"Dear Dr. {t.author_name.split()[-1]},\n\n"
        f"I recently studied your work, '{t.paper_title}', particularly the limitation that: {t.gap_evidence}\n\n"
        f"{pitch}\n\n"
        f"{applicant_profile}\n\n"
        f"I would be very interested in discussing a stipend-based research internship under your supervision, with the goal of generating fresh experimental data and, if the results support it, contributing to a joint publication. Would you be open to a 15-minute call?\n\n"
        f"Best regards,\nDheeraj Kumar"
    )
