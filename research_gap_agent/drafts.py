from __future__ import annotations


def build_experiment(gap: dict, technology_name: str) -> str:
    gap_type = gap.get("gap_type", "methodological limitation")
    capability = gap.get("capability", "the demonstrated technology")
    return (
        f"Test whether {capability} can address the paper's {gap_type} constraint using a controlled comparison "
        f"against the study's reported reference method, with the proposed {technology_name} as the intervention."
    )


def build_pitch(author_name: str, paper: dict, technology_name: str) -> str:
    gaps = paper.get("gaps") or []
    gap = gaps[0] if gaps else {}
    evidence = gap.get("evidence", "")
    experiment = build_experiment(gap, technology_name)
    return (
        f"I studied your paper, '{paper.get('title', 'your recent work')}', and focused on the methodological issue reflected in: {evidence} "
        f"I have developed {technology_name}. The closest research bridge is: {experiment} "
        "This would provide a focused validation experiment rather than treating the technology as a generic replacement."
    )


def build_email(author_name: str, affiliation: str, paper: dict, technology_name: str, applicant_profile: str = "") -> str:
    last = (author_name.split() or ["Researcher"])[-1]
    pitch = build_pitch(author_name, paper, technology_name)
    profile = applicant_profile.strip() or "I am interested in a research internship focused on implementing and experimentally validating this extension."
    return (
        f"Subject: Research internship idea building on your work\n\n"
        f"Dear Dr. {last},\n\n"
        f"{pitch}\n\n"
        f"{profile}\n\n"
        "I would be glad to discuss whether this is a useful direction for your group, including a defined experimental plan and the possibility of contributing data and analysis toward a publication if the results justify it.\n\n"
        "Best regards,\nDheeraj Kumar"
    )
