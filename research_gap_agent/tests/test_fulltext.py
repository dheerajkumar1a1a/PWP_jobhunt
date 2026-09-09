from research_gap_agent.fulltext import extract_html_text, locate_gap_sentences


def test_extract_html_text_removes_markup():
    text = extract_html_text(b"<html><body><h1>Title</h1><p>Future work is needed.</p></body></html>")
    assert "Title" in text
    assert "Future work is needed." in text
    assert "<p>" not in text


def test_locate_gap_sentences():
    evidence = locate_gap_sentences("This method is useful. The assay is destructive and laborious. Future work should develop a portable method.")
    assert len(evidence) >= 2
