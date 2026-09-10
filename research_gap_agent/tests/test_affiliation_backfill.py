from research_gap_agent import cli
from research_gap_agent.researchers import aggregate_researchers


def _target(affiliations=None):
    return {
        "author_name": "U. Alshana",
        "affiliations": affiliations if affiliations is not None else [],
        "paper_count": 1,
        "researcher_score": 75.0,
        "papers": [{
            "title": "Smartphone colorimetry of extracts",
            "doi": "10.1/x",
            "score": 80.0,
            "gaps": [{"evidence": "laboratory assay", "gap_type": "laboratory", "capability": "portable"}],
            "authors": [{"name": "U. Alshana", "institution": ""}],
        }],
    }


def _match():
    return {"display_name": "U. Alshana", "last_known_institutions": [{"display_name": "Gazi University"}]}


def test_aggregate_keeps_paper_authors():
    papers = [{"title": "T", "doi": "D", "score": 80.0, "gaps": [], "authors": [{"name": "A. R.", "institution": "Uni"}]}]
    targets = aggregate_researchers(papers, minimum_score=70.0)
    assert targets and targets[0]["papers"][0]["authors"] == [{"name": "A. R.", "institution": "Uni"}]


def test_target_affiliations_backfilled(monkeypatch):
    monkeypatch.setattr(cli, "enrich_author", lambda a: {**a, "public_email": None, "profile_url": None, "verified_public_institutional": False})
    monkeypatch.setattr(cli, "search_openalex_author", lambda name: _match())
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    out, _, _ = cli.add_drafts_and_contacts([_target()], "proj", {})
    assert out[0]["affiliations"] == ["Gazi University"]


def test_no_lookup_when_affiliations_present(monkeypatch):
    monkeypatch.setattr(cli, "enrich_author", lambda a: {**a, "public_email": None, "profile_url": None, "verified_public_institutional": False})

    def _boom(name):
        raise AssertionError("no author search needed when affiliations exist")

    monkeypatch.setattr(cli, "search_openalex_author", _boom)
    out, _, _ = cli.add_drafts_and_contacts([_target(affiliations=["Known Uni"])], "proj", {})
    assert out[0]["affiliations"] == ["Known Uni"]


def test_merged_authors_reach_enrichment(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "enrich_author", lambda a: seen.append(a["name"]) or {**a, "public_email": "u@gazi.edu.tr", "profile_url": "https://gazi.edu.tr", "verified_public_institutional": True})
    monkeypatch.setattr(cli, "search_openalex_author", lambda name: None)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    out, verified, _ = cli.add_drafts_and_contacts([_target()], "proj", {})
    assert seen == ["U. Alshana"]
    assert out[0]["public_email"] == "u@gazi.edu.tr"
    assert verified == 1
