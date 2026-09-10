import research_gap_agent.author_enrichment as ae
from research_gap_agent.enrichment import extract_public_email, find_named_emails, find_named_institutional_email

MATCH = {
    "id": "https://openalex.org/A1",
    "display_name": "Test Author",
    "last_known_institutions": [{"id": "https://openalex.org/I1", "display_name": "Test University"}],
}
WORKS = {"results": [{
    "title": "Paper One",
    "locations": [
        {"pdf_url": "https://pubs.acs.org/doi/pdf/x", "source": {"display_name": "ACS"}},
        {"pdf_url": "https://repo.testuni.edu/paper.pdf", "source": {"display_name": "TestUni Repo"}},
    ],
}]}


def _wire(monkeypatch, pdf_text, homepage="https://www.testuni.edu/"):
    monkeypatch.setattr(ae, "fetch_openalex_author", lambda aid: MATCH)
    monkeypatch.setattr(ae, "institution_homepage", lambda iid: homepage)
    monkeypatch.setattr(ae.scholarly, "get_json", lambda url, retries=3, headers=None: WORKS)
    monkeypatch.setattr(ae, "fetch_public_text", lambda url, timeout=20: pdf_text)
    monkeypatch.setattr(ae.time, "sleep", lambda s: None)


def test_correspondence_hit_prefers_repository_copy(monkeypatch):
    _wire(monkeypatch, "Test Author et al. Corresponding author: t.author@testuni.edu. editor@elsevier.com")
    hit = ae.correspondence_from_oa_works("Test Author", "https://openalex.org/A1")
    assert hit is not None
    assert hit["public_email"] == "t.author@testuni.edu"
    assert hit["verified_public_institutional"] is True
    assert hit["profile_url"] == "https://repo.testuni.edu/paper.pdf"
    assert hit["contact_source"] == "paper_pdf_correspondence"


def test_correspondence_rejects_foreign_domain(monkeypatch):
    _wire(monkeypatch, "Test Author et al. Write to t.author@other.edu for data.")
    assert ae.correspondence_from_oa_works("Test Author", "https://openalex.org/A1") is None


def test_correspondence_rejects_unattributable(monkeypatch):
    _wire(monkeypatch, "Test Author et al. Contact editor@elsevier.com for copies.")
    assert ae.correspondence_from_oa_works("Test Author", "https://openalex.org/A1") is None


def test_correspondence_bails_without_institution_domain(monkeypatch):
    _wire(monkeypatch, "t.author@testuni.edu", homepage="")
    assert ae.correspondence_from_oa_works("Test Author", "https://openalex.org/A1") is None


def test_extract_public_email_rejects_asset_urls():
    html = ('<img src="https://orcid.org/a/flags@2x.9790563a0e331d13.webp">'
            ' contact <a href="mailto:a.b@uni.edu">here</a>')
    assert extract_public_email(html) == "a.b@uni.edu"
    assert extract_public_email('<img src="https://x.org/p/flags@2x.abc123.webp">') is None


def test_find_named_institutional_email():
    html = ('Contact our lab: <a href="mailto:georgina.ross@wur.nl">mail</a> '
            "webmaster@wur.nl info@gmail.com")
    assert find_named_institutional_email(html, "Georgina M.S. Ross", {"wur.nl"}) == "georgina.ross@wur.nl"
    assert find_named_institutional_email(html, "Yunfeng Zhao", {"wur.nl"}) is None
    assert find_named_institutional_email(html, "Georgina M.S. Ross", {"qub.ac.uk"}) is None


LAB_PAGES = {
    "https://lab.testuni.edu/": '<a href="/people">People</a><a href="https://external.org/team">Team</a>',
    "https://lab.testuni.edu/people": "Our team: Test Author <a href=\"mailto:t.author@testuni.edu\">email</a>",
}


def test_lab_crawl_follows_same_host_contact_link(monkeypatch):
    fetched = []
    monkeypatch.setattr(ae, "fetch_openalex_author", lambda aid: MATCH)
    monkeypatch.setattr(ae, "institution_homepage", lambda iid: "https://www.testuni.edu/")

    def fake_fetch(url, timeout=20):
        fetched.append(url)
        return LAB_PAGES[url]

    monkeypatch.setattr(ae, "fetch_text", fake_fetch)
    monkeypatch.setattr(ae.time, "sleep", lambda s: None)
    hit = ae.lab_contact_crawl("Test Author", ["https://lab.testuni.edu/"], "https://openalex.org/A1")
    assert hit is not None
    assert hit["public_email"] == "t.author@testuni.edu"
    assert hit["contact_source"] == "lab_website_contact"
    assert hit["profile_url"] == "https://lab.testuni.edu/people"
    assert "https://external.org/team" not in fetched


def test_lab_crawl_respects_fetch_cap(monkeypatch):
    pages = {"https://lab.testuni.edu/": "".join(f'<a href="/c{i}">c{i}</a>' for i in range(30))}
    pages.update({f"https://lab.testuni.edu/c{i}": "no emails here" for i in range(30)})
    fetched = []
    monkeypatch.setattr(ae, "fetch_openalex_author", lambda aid: MATCH)
    monkeypatch.setattr(ae, "institution_homepage", lambda iid: "https://www.testuni.edu/")
    monkeypatch.setattr(ae, "fetch_text", lambda url, timeout=20: fetched.append(url) or pages[url])
    monkeypatch.setattr(ae.time, "sleep", lambda s: None)
    assert ae.lab_contact_crawl("Test Author", ["https://lab.testuni.edu/"], "https://openalex.org/A1") is None
    assert len(fetched) <= ae.LAB_CRAWL_FETCH_CAP


def test_europepmc_hit(monkeypatch):
    monkeypatch.setattr(ae, "fetch_openalex_author", lambda aid: MATCH)
    monkeypatch.setattr(ae, "institution_homepage", lambda iid: "https://www.testuni.edu/")

    def fake_get(url, retries=3, headers=None):
        assert "ORCID" in url and "0000-0001-2345-6789" in url
        return {"resultList": {"result": [{
            "source": "MED", "id": "123",
            "affiliation": "Dept X, Test University. Electronic address: t.author@testuni.edu.",
        }]}}

    monkeypatch.setattr(ae.scholarly, "get_json", fake_get)
    hit = ae.europepmc_affiliation_email("Test Author", orcid="0000-0001-2345-6789", author_id="https://openalex.org/A1")
    assert hit is not None
    assert hit["public_email"] == "t.author@testuni.edu"
    assert hit["contact_source"] == "europepmc_affiliation"
    assert hit["profile_url"] == "https://europepmc.org/article/MED/123"


def test_europepmc_requires_orcid():
    assert ae.europepmc_affiliation_email("Test Author") is None


def test_find_named_emails_collects_any_domain():
    html = ("Write to georgina.ross@wur.nl or georgina.ross@gmail.com "
            "or editor@elsevier.com; webmaster@wur.nl keeps the site.")
    assert find_named_emails(html, "Georgina M.S. Ross") == ["georgina.ross@wur.nl"]
    assert find_named_emails(html, "Yunfeng Zhao") == []


def test_resolve_collects_candidates_without_verifying(monkeypatch):
    from research_gap_agent import enrichment as en
    html = 'Lab contact: <a href="mailto:t.author@random.org">mail</a>'
    monkeypatch.setattr(en, "fetch_text", lambda url, timeout=20: html)
    collected: list[dict] = []
    profile = en.resolve_public_profile("Test Author", "Test University", ["https://lab.example.org/"], collected)
    assert profile.verified_public_institutional is False
    assert collected == [{"email": "t.author@random.org", "url": "https://lab.example.org/", "source": "public_profile_page", "verified": False}]
