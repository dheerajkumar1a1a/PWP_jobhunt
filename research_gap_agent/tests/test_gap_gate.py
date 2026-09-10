from research_gap_agent.gap_engine import EXPLORATORY_CAP, score_paper

CAPS = {"smartphone_based": True, "non_destructive": True, "portable": True}


def test_non_destructive_self_description_is_not_a_gap():
    # The Zhengao Li case: paper describes ITSELF as non-destructive.
    score, results = score_paper(
        "Explainable AI and mobile imaging for non-destructive avocado ripeness assessment",
        "In this study, we integrated smartphone imaging and deep learning to non-destructively predict avocado firmness and internal quality.",
        CAPS,
    )
    assert score == 0
    assert results == []


def test_explicit_limitation_scores_promising():
    score, results = score_paper(
        "Smartphone colorimetry",
        "The current laboratory assay is expensive and destructive. A portable non-destructive smartphone colorimetric method would address this limitation.",
        CAPS,
    )
    assert score >= 65
    assert any(r.explicit_limitation for r in results)


def test_methodological_constraint_without_explicit_language_is_capped():
    score, results = score_paper(
        "Smartphone colorimetry",
        "The current laboratory assay is expensive and destructive. A portable non-destructive smartphone colorimetric method would address this.",
        CAPS,
    )
    assert 0 < score <= EXPLORATORY_CAP
    assert results and results[0].explicit_limitation is False
