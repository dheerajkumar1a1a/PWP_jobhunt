from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class GapResult:
    gap_type: str
    evidence: str
    capability: str
    bridge: str
    gap_strength: float
    capability_strength: float
    bridge_strength: float
    score: float


GAP_PATTERNS = {
    "destructive": [r"destructive", r"requires? (?:sample )?(?:extraction|juice|cutting|crushing)", r"destroy(?:s|ed|ing)? the sample"],
    "laboratory": [r"laborator(?:y|ies)", r"spectrophotometer", r"chromatograph", r"reagent", r"chemical assay"],
    "slow": [r"time[- ]consuming", r"laborious", r"requires? (?:waiting|heating)", r"long (?:analysis|processing) time"],
    "manual": [r"manual", r"subjective", r"operator[- ]dependent", r"requires? (?:expert|skilled)"],
    "expensive": [r"expensive", r"high[- ]cost", r"costly", r"specialized equipment"],
    "nonportable": [r"not portable", r"laboratory[- ]based", r"bench[- ]top", r"bulky"],
    "imaging": [r"segmentation", r"computer vision", r"image processing", r"deep learning", r"convolutional"],
    "colorimetric": [r"colorimetr", r"colourimetr", r"cielab", r"l\*", r"a\*", r"b\*", r"delta.?e", r"Δe"],
    "validation": [r"limitation", r"challenge", r"future work", r"remain(?:s|ed)?", r"further (?:work|validation)", r"need(?:s)? to be (?:developed|validated|investigated)"],
}

CAPABILITY_TERMS = {
    "non_destructive": [r"non[- ]destructive", r"intact sample", r"without (?:destroying|cutting|extracting)"],
    "smartphone_based": [r"smartphone", r"mobile phone", r"phone camera"],
    "low_cost": [r"low[- ]cost", r"inexpensive", r"affordable"],
    "portable": [r"portable", r"field[- ]deployable", r"on[- ]site"],
    "fixed_sample_distance": [r"fixed distance", r"controlled distance", r"standardized distance"],
    "image_segmentation": [r"segmentation", r"mask", r"region of interest", r"roi"],
    "irregular_object_segmentation": [r"irregular shape", r"irregular object", r"contour", r"shape-independent"],
    "cpu_only": [r"cpu", r"edge device", r"resource[- ]constrained"],
    "sub_second_analysis_target": [r"real[- ]time", r"sub[- ]second", r"milliseconds", r"instant"],
    "absolute_cielab": [r"cielab", r"l\*", r"a\*", r"b\*"],
    "differential_colorimetry": [r"differential color", r"color difference", r"delta.?e", r"Δe"],
    "biochemical_gradient_correlation": [r"gradient", r"correlation", r"biochemical", r"chemical concentration", r"pyruvic acid"],
    "comparative_classification": [r"classification", r"ranking", r"comparative", r"relative"],
    "agricultural_food_application": [r"food", r"agricultur", r"postharvest", r"quality", r"breeding"],
}


def _hits(text: str, patterns: Iterable[str]) -> list[str]:
    out: list[str] = []
    for p in patterns:
        if re.search(p, text, re.I):
            out.append(p)
    return out


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract_gap_evidence(text: str) -> list[str]:
    sentences = split_sentences(text)
    hits: list[str] = []
    for s in sentences:
        if any(re.search(p, s, re.I) for p in GAP_PATTERNS["validation"]):
            hits.append(s[:500])
        elif any(re.search(p, s, re.I) for p in GAP_PATTERNS["destructive"] + GAP_PATTERNS["laboratory"] + GAP_PATTERNS["slow"] + GAP_PATTERNS["manual"] + GAP_PATTERNS["expensive"] + GAP_PATTERNS["nonportable"]):
            hits.append(s[:500])
    return hits[:5]


def score_paper(title: str, abstract: str, capabilities: dict[str, bool]) -> tuple[float, list[GapResult]]:
    text = f"{title}. {abstract}".strip()
    evidences = extract_gap_evidence(text)
    results: list[GapResult] = []
    for sentence in evidences:
        matched_gap_types = [k for k, pats in GAP_PATTERNS.items() if k != "validation" and _hits(sentence, pats)]
        matched_caps = [k for k, enabled in capabilities.items() if enabled and _hits(sentence, CAPABILITY_TERMS.get(k, []))]
        # Also allow a capability match elsewhere in the paper, but require gap evidence in the same paper.
        full_caps = [k for k, enabled in capabilities.items() if enabled and _hits(text, CAPABILITY_TERMS.get(k, []))]
        caps = matched_caps or full_caps[:4]
        if not matched_gap_types or not caps:
            continue
        gap_strength = min(1.0, 0.75 + 0.08 * len(matched_gap_types))
        capability_strength = min(1.0, 0.60 + 0.08 * len(caps))
        bridge_strength = min(1.0, 0.55 + 0.10 * min(len(matched_gap_types), len(caps)))
        score = round(35 * gap_strength + 30 * capability_strength + 15 * bridge_strength + 10 * (1.0 if any(k in caps for k in ("agricultural_food_application", "comparative_classification")) else 0.4), 2)
        results.append(GapResult(matched_gap_types[0], sentence, caps[0], f"Test the baseline capability '{caps[0]}' against the paper's '{matched_gap_types[0]}' constraint.", gap_strength, capability_strength, bridge_strength, score))
    results.sort(key=lambda r: r.score, reverse=True)
    return (results[0].score if results else 0.0), results[:5]


def to_dict(result: GapResult) -> dict:
    return asdict(result)
