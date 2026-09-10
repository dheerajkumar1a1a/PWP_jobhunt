from research_gap_agent import enrichment as en
from research_gap_agent import openrouter_free as orf
from research_gap_agent.draft_builder import build_email, build_pitch, validate_draft


def test_resolver_skips_unverified_first_url(monkeypatch):
    pages = {
        "https://biguni.edu": "<html>Welcome to Big University. webmaster@example.org</html>",
        "https://lab.biguni.edu/~ada": "<html>Contact: ada@lab.biguni.edu</html>",
    }
    monkeypatch.setattr(en, "fetch_text", lambda url, timeout=20: pages[url])
    out = en.resolve_public_profile("Ada Lovelace", "", ["https://biguni.edu", "https://lab.biguni.edu/~ada"])
    assert out.verified_public_institutional is True
    assert out.email == "ada@lab.biguni.edu"
    assert out.profile_url == "https://lab.biguni.edu/~ada"


def test_resolver_strict_when_nothing_verifies(monkeypatch):
    monkeypatch.setattr(en, "fetch_text", lambda url, timeout=20: "<html>Contact: someone@gmail.com</html>")
    out = en.resolve_public_profile("Ada", "", ["https://biguni.edu"])
    assert out.verified_public_institutional is False
    assert out.email is None


def test_validate_draft_rejects_identity_confusion():
    bad = "Dear Prof. Sun,\n\nI am Ying Fu, a researcher at BIT.\n\nSincerely,\nYing Fu"
    assert validate_draft(bad, "Ying Fu") is False


def test_validate_draft_rejects_missing_signature():
    assert validate_draft("Dear Dr. Lee,\n\nGreat paper.\n\nBest regards", "In-Hwan Lee") is False
    assert validate_draft("", "In-Hwan Lee") is False


def test_validate_draft_accepts_good_draft():
    good = "Dear Dr. Lee,\n\nI read your paper with interest.\n\nBest regards,\nDheeraj Kumar"
    assert validate_draft(good, "In-Hwan Lee") is True


def test_email_states_paper_title_once_not_twice():
    email = build_email("A. Geballa", "Smartphone sensors part 1", "Lab gear is expensive.", "laboratory", "smartphone_based", "Onion Layers")
    assert email.count("Smartphone sensors part 1") == 1
    assert email.count("Lab gear is expensive.") == 1
    assert "My current project, 'Onion Layers', provides a smartphone based capability" in email
    assert validate_draft(email, "A. Geballa") is True


def test_pitch_standalone_keeps_title_and_evidence():
    pitch = build_pitch("A. Geballa", "Smartphone sensors part 1", "Lab gear is expensive.", "laboratory", "smartphone_based", "Onion Layers")
    assert "Smartphone sensors part 1" in pitch
    assert "Lab gear is expensive." in pitch
    assert "smartphone_based" not in pitch


def test_prompt_anchors_identity(monkeypatch):
    captured = {}

    def _chat(system, user, max_tokens=900):
        captured["s"] = system
        captured["u"] = user
        return "ok"

    monkeypatch.setattr(orf, "chat", _chat)
    orf.draft_email({"objective": "x"}, {"name": "Ying Fu"}, {"title": "T"}, {"gap_type": "lab"})
    assert "Dheeraj Kumar" in captured["s"]
    assert "NOT the researcher" in captured["s"]
    assert "YOUR OWN results" in captured["s"]
    assert "applicant_name" in captured["u"]
