from research_gap_agent import author_backfill as bb
from research_gap_agent import author_enrichment as ae


def _author_record(orcid="https://orcid.org/0000-0001-2345-6789"):
    return {
        "results": [{
            "display_name": "U. Alshana",
            "orcid": orcid,
            "works_count": 40,
            "cited_by_count": 500,
            "last_known_institutions": [{
                "display_name": "Gazi University",
                "homepage_url": "https://gazi.edu.tr",
            }],
        }],
    }


def test_backfill_collects_homepage_and_orcid_urls(monkeypatch):
    monkeypatch.setattr(bb.scholarly, "get_json", lambda url, retries=3, headers=None: (
        {"researcher-url": [{"url": {"value": "https://alshana-lab.org"}}]}
        if "orcid.org" in url else _author_record()
    ))
    urls, institution = bb.backfill_profile_urls("U. Alshana")
    assert urls[0] == "https://gazi.edu.tr"
    assert "https://alshana-lab.org" in urls
    assert institution == "Gazi University"


def test_backfill_refuses_on_affiliation_mismatch(monkeypatch):
    monkeypatch.setattr(bb.scholarly, "get_json", lambda url, retries=3, headers=None: _author_record())
    urls, institution = bb.backfill_profile_urls("U. Alshana", affiliation="University of Tokyo")
    assert urls == [] and institution == ""


def test_backfill_empty_when_no_match(monkeypatch):
    monkeypatch.setattr(bb.scholarly, "get_json", lambda url, retries=3, headers=None: {"results": []})
    assert bb.backfill_profile_urls("Nobody Unknown") == ([], "")


def test_enrich_author_uses_backfill_then_verifies(monkeypatch):
    monkeypatch.setattr(ae, "backfill_profile_urls", lambda name, aff="": (["https://gazi.edu.tr"], "Gazi University"))
    monkeypatch.setattr(
        "research_gap_agent.enrichment.fetch_text",
        lambda url, timeout=20: "<html>Contact: u.alshana@gazi.edu.tr</html>",
    )
    out = ae.enrich_author({"name": "U. Alshana", "institution": ""})
    assert out["public_email"] == "u.alshana@gazi.edu.tr"
    assert out["verified_public_institutional"] is True
    assert out["profile_backfilled"] is True


def test_enrich_author_skips_backfill_when_urls_present(monkeypatch):
    called = []

    def _boom(name, aff=""):
        called.append(name)
        raise AssertionError("backfill must not run when URLs exist")

    monkeypatch.setattr(ae, "backfill_profile_urls", _boom)
    monkeypatch.setattr(
        "research_gap_agent.enrichment.fetch_text",
        lambda url, timeout=20: "<html>Contact: someone@uni.edu</html>",
    )
    out = ae.enrich_author({"name": "A. Researcher", "institution": "", "profile_url": "https://uni.edu/~a"})
    assert called == []
    assert out["profile_backfilled"] is False
