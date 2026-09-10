import urllib.parse as up

from research_gap_agent import author_backfill as bb
from research_gap_agent import author_enrichment as ae


def _author_record(orcid="https://orcid.org/0000-0001-2345-6789", inst_id="https://openalex.org/I123"):
    return {
        "results": [{
            "id": "https://openalex.org/A999",
            "display_name": "U. Alshana",
            "orcid": orcid,
            "works_count": 40,
            "cited_by_count": 500,
            "last_known_institutions": [{
                "id": inst_id,
                "display_name": "Gazi University",
            }],
        }],
    }


def _dispatch(monkeypatch, calls=None, orcid_urls=True, s2_homepage=""):
    def fake_get_json(url, retries=3, headers=None):
        if calls is not None:
            calls.append(url)
        if "authors?search=" in url:
            return _author_record()
        if "/I123" in url:
            return {"display_name": "Gazi University", "homepage_url": "https://gazi.edu.tr"}
        if "pub.orcid.org" in url:
            return {"researcher-url": [{"url": {"value": "https://alshana-lab.org"}}]} if orcid_urls else {}
        if "api.semanticscholar.org/graph/v1/author/" in url:
            return {"name": "U. Alshana", "homepage": s2_homepage}
        if url in ("https://openalex.org/A999", "https://api.openalex.org/A999"):
            return _author_record()["results"][0]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(bb.scholarly, "get_json", fake_get_json)


def setup_function(_):
    bb._INST_HOMEPAGE_CACHE.clear()


def test_backfill_collects_homepage_and_orcid_urls(monkeypatch):
    _dispatch(monkeypatch)
    urls, institution = bb.backfill_profile_urls("U. Alshana")
    assert urls[0] == "https://gazi.edu.tr"
    assert "https://alshana-lab.org" in urls
    assert institution == "Gazi University"


def test_backfill_refuses_on_affiliation_mismatch(monkeypatch):
    _dispatch(monkeypatch)
    urls, institution = bb.backfill_profile_urls("U. Alshana", affiliation="University of Tokyo")
    assert urls == [] and institution == ""


def test_backfill_empty_when_no_match(monkeypatch):
    monkeypatch.setattr(bb.scholarly, "get_json", lambda url, retries=3, headers=None: {"results": []})
    assert bb.backfill_profile_urls("Nobody Unknown") == ([], "")


def test_direct_openalex_id_skips_search(monkeypatch):
    calls = []
    _dispatch(monkeypatch, calls)
    urls, _ = bb.backfill_profile_urls("Anyone Atall", author_id="https://openalex.org/A999")
    assert not any("authors?search=" in c for c in calls)
    assert "https://gazi.edu.tr" in urls


def test_s2_homepage_included_for_numeric_author_id(monkeypatch):
    _dispatch(monkeypatch, s2_homepage="https://lab.example.edu/~u")
    urls, _ = bb.backfill_profile_urls("U. Alshana", author_id="12345")
    assert "https://lab.example.edu/~u" in urls


def test_institution_homepage_cached(monkeypatch):
    calls = []
    _dispatch(monkeypatch, calls)
    bb.backfill_profile_urls("U. Alshana")
    bb.backfill_profile_urls("U. Alshana")
    assert sum("/I123" in c for c in calls) == 1


def test_enrich_author_uses_backfill_then_verifies(monkeypatch):
    monkeypatch.setattr(ae, "backfill_profile_urls", lambda name, aff="", author_id=None: (["https://gazi.edu.tr"], "Gazi University"))
    monkeypatch.setattr(
        "research_gap_agent.enrichment.fetch_text",
        lambda url, timeout=20: "<html>Contact: u.alshana@gazi.edu.tr</html>",
    )
    out = ae.enrich_author({"name": "U. Alshana", "institution": ""})
    assert out["public_email"] == "u.alshana@gazi.edu.tr"
    assert out["verified_public_institutional"] is True
    assert out["profile_backfilled"] is True
    assert out["institution"] == "Gazi University"


def test_enrich_author_skips_backfill_when_urls_present(monkeypatch):
    called = []

    def _boom(name, aff="", author_id=None):
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
