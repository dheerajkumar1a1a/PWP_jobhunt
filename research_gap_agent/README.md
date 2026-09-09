# $0 Research-Gap Internship Agent

A free-first literature-to-researcher discovery pipeline. It treats a research project as a technology baseline, discovers scholarly work, extracts evidence-backed research gaps, maps those gaps to project capabilities, ranks researchers, and produces human-reviewable internship/co-authorship drafts.

**Outreach rule:** discovery and drafting are automated; outreach is never sent automatically.

## Pipeline

`technology_spec.yaml` → OpenAlex/Crossref/Semantic Scholar → gap evidence → capability match → public-full-text deep analysis → researcher aggregation → public-contact enrichment → personalized pitch/email → human review → Telegram tracking.

## Free-first design

- Python + SQLite + PyYAML + pytest + pypdf.
- Scholarly discovery uses free/public metadata endpoints subject to provider rate limits and terms.
- Public full text is used only when an explicit public PDF/HTML URL is exposed; the agent does not bypass paywalls.
- No paid LLM is required. Deterministic scoring/drafting is the default.
- A local LLM can optionally be added later without storing a paid API key in GitHub.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m research_gap_agent.cli scan --config research_gap_agent/config/technology_spec.yaml
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m research_gap_agent.cli scan --config research_gap_agent/config/technology_spec.yaml
```

## GitHub Actions

`.github/workflows/research_gap_scan.yml` runs weekly and supports manual dispatch. It installs dependencies, runs unit tests, performs multi-source academic discovery, analyzes a bounded number of publicly exposed full texts, generates a research-gap report, sends Telegram tracking notifications when the two Telegram secrets are present, and uploads the SQLite/Markdown review package. It never sends researcher outreach.

## Scoring philosophy

A paper is a serious target only when its text contains an explicit or strongly evidenced limitation that maps to one or more baseline capabilities. Title similarity alone is insufficient. High scores require evidence of a limitation, direct capability coverage, a plausible experimental bridge, and identifiable author ownership.

Suggested thresholds:

- 80–100: priority target; manual verification recommended
- 65–79: promising; inspect paper/full text and author lab
- 50–64: exploratory
- <50: reject from outreach queue

## Human review gate

Every candidate remains `pending` until a person verifies the original paper, exact gap evidence, author identity/affiliation, public institutional contact, and proposed experiment. Email drafts are stored for review and are not sent automatically.
