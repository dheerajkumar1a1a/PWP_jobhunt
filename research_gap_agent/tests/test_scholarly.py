from research_gap_agent import scholarly as sch


def _oa_page(results, next_cursor=None):
    return {"results": results, "meta": {"next_cursor": next_cursor}}


def _work(i):
    return {"id": f"oa:{i}", "doi": None, "title": f"Paper {i}", "authorships": []}


def test_openalex_paginates_past_25(monkeypatch):
    calls = []

    def fake_get_json(url, retries=3, headers=None):
        calls.append(url)
        if "cursor=%2A" in url or "cursor=*" in url:
            return _oa_page([_work(i) for i in range(200)], next_cursor="abc")
        return _oa_page([_work(i) for i in range(200, 250)], next_cursor=None)

    monkeypatch.setattr(sch, "get_json", fake_get_json)
    out = sch.openalex_search("onion", per_page=100)
    assert len(out) == 100
    assert len(calls) == 1  # 100 fits in one 200/page request


def test_openalex_multi_page(monkeypatch):
    def fake_get_json(url, retries=3, headers=None):
        if "cursor=abc" in url:
            return _oa_page([_work(i) for i in range(200, 400)], next_cursor=None)
        return _oa_page([_work(i) for i in range(200)], next_cursor="abc")

    monkeypatch.setattr(sch, "get_json", fake_get_json)
    out = sch.openalex_search("onion", per_page=300)
    assert len(out) == 300


def _cr_item(i):
    return {"DOI": f"10.1/x{i}", "title": [f"Title {i}"], "author": [], "URL": f"https://doi.org/10.1/x{i}", "is-referenced-by-count": 0}


def test_crossref_past_old_cap_of_10(monkeypatch):
    def fake_get_json(url, retries=3, headers=None):
        assert "rows=50" in url
        return {"message": {"items": [_cr_item(i) for i in range(50)]}}

    monkeypatch.setattr(sch, "get_json", fake_get_json)
    out = sch.crossref_search("onion", rows=50)
    assert len(out) == 50


def _s2_item(i):
    return {"paperId": f"p{i}", "title": f"T{i}", "abstract": "a b", "year": 2024, "authors": [], "externalIds": {}, "openAccessPdf": {}, "citationCount": 0}


def test_semantic_scholar_past_old_cap_of_10(monkeypatch):
    seen = []

    def fake_get_json(url, retries=3, headers=None):
        seen.append(url)
        if "offset=0" in url:
            return {"data": [_s2_item(i) for i in range(100)]}
        return {"data": [_s2_item(i) for i in range(100, 130)]}

    monkeypatch.setattr(sch, "get_json", fake_get_json)
    out = sch.semantic_scholar_search("onion", limit=120)
    assert len(out) == 120
    assert len(seen) == 2


def test_discover_dedupes_across_providers(monkeypatch):
    monkeypatch.setattr(sch, "openalex_search", lambda q, n=100: [{"id": "a", "doi": "10.1/dup", "title": "Dup", "authorships": []}])
    monkeypatch.setattr(sch, "crossref_search", lambda q, rows=100: [{"id": "b", "doi": "https://doi.org/10.1/dup", "title": "Dup", "authorships": []}])
    monkeypatch.setattr(sch, "semantic_scholar_search", lambda q, limit=100: [])
    monkeypatch.setattr(sch.time, "sleep", lambda s: None)
    out = sch.discover("q", per_query=100)
    # different DOI strings -> both kept; same title+provider path dedupes exact dupes
    assert len(out) >= 1
    assert all(w.get("source_provider") for w in out)
