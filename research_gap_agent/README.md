# $0 Research-Gap Internship Agent

A free-first literature-to-researcher discovery pipeline. It treats a research project as a **technology baseline**, searches academic metadata, extracts evidence-backed research gaps, scores whether the baseline directly closes those gaps, resolves authors/affiliations, and produces human-reviewable internship/co-authorship outreach drafts.

**Safety rule:** discovery and drafting are automated; outreach is never sent automatically.

## Pipeline

`technology_spec.yaml` → query generation → OpenAlex/Crossref → evidence filter → gap/capability scoring → author aggregation → public institutional contact verification → pitch/email drafts → SQLite/CSV review queue.

## $0 design

- Python standard library + `requests` + `PyYAML` + `pandas` only.
- OpenAlex and Crossref are used as free scholarly metadata sources; their terms/rate limits still apply.
- No paid LLM is required. Deterministic extraction/scoring is the default.
- Optional local LLM support can be added later (e.g. Ollama) without putting an API key in GitHub.
- GitHub Actions schedules the scan and stores compact artifacts; SQLite is the local/state database.

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

The workflow in `.github/workflows/research_gap_scan.yml` runs weekly and can be started manually. It performs discovery only and uploads a review artifact. It does **not** send email.

## Scoring philosophy

A paper is a serious target only when its text contains an explicit or strongly evidenced limitation that maps to one or more baseline capabilities. Title similarity alone is insufficient. High scores require: (1) evidence of a limitation, (2) direct capability coverage, (3) plausible experimental bridge, and (4) identifiable author ownership of the research line.

Suggested thresholds:

- 80–100: priority target; manual verification recommended
- 65–79: promising; inspect paper/full text and author lab
- 50–64: exploratory
- <50: reject from outreach queue

## Human review gate

Every generated contact record has `review_status=pending`. A person must verify the paper, the claimed gap, the affiliation, the public institutional email, and the proposed experiment before any outreach is sent.
