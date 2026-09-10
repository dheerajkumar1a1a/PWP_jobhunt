from research_gap_agent import fulltext
from research_gap_agent.fulltext import extract_html_text, extract_pdf_text, fetch_public_text, locate_gap_sentences


def test_extract_html_text_removes_markup():
    text = extract_html_text(b"<html><body><h1>Title</h1><p>Future work is needed.</p></body></html>")
    assert "Title" in text
    assert "Future work is needed." in text
    assert "<p>" not in text


def test_locate_gap_sentences():
    evidence = locate_gap_sentences("This method is useful. The assay is destructive and laborious. Future work should develop a portable method.")
    assert len(evidence) >= 2


def test_extract_pdf_text_rejects_html_quietly(recwarn):
    assert extract_pdf_text(b"<!doctype html><html><body>paywall</body></html>") == ""
    assert extract_pdf_text(b"junk-bytes") == ""
    assert list(recwarn) == []


def test_fetch_public_text_falls_back_to_html(monkeypatch):
    monkeypatch.setattr(
        fulltext, "fetch_bytes",
        lambda url, timeout=20: (b"<html><body>Future work is needed.</body></html>", "application/pdf"),
    )
    assert "Future work is needed." in fetch_public_text("https://example.org/paper.pdf")


def test_fetch_public_text_never_raises(monkeypatch):
    def _boom(url, timeout=20):
        raise ConnectionResetError("reset")
    monkeypatch.setattr(fulltext, "fetch_bytes", _boom)
    assert fetch_public_text("https://example.org/paper.pdf") == ""
