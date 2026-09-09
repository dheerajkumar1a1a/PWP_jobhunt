from research_gap_agent.gap_engine import extract_gap_evidence, score_paper


def test_explicit_gap_is_extracted():
    text = "The method is laborious and requires laboratory equipment. Future work should develop a portable approach."
    evidence = extract_gap_evidence(text)
    assert evidence
    assert any("laborious" in x.lower() or "future work" in x.lower() for x in evidence)


def test_gap_without_capability_does_not_score():
    score, results = score_paper(
        "An unrelated study",
        "The study has a limitation and future work is needed.",
        {"smartphone_based": True, "non_destructive": True},
    )
    assert score == 0
    assert results == []


def test_direct_capability_gap_scores():
    score, results = score_paper(
        "Smartphone colorimetry",
        "The current laboratory assay is expensive and destructive. A portable non-destructive smartphone colorimetric method would address this limitation.",
        {"smartphone_based": True, "non_destructive": True, "portable": True},
    )
    assert score > 0
    assert results
    assert results[0].gap_type in {"destructive", "laboratory", "expensive", "nonportable"}
