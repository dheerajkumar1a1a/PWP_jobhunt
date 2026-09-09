# jobhunt

A personal job-search agent. It reads public ATS APIs every morning, filters and ranks roles, drafts an application kit, and emails a digest. **It never submits an application.**

## Research-gap internship discovery

This repository also contains a free-first research internship discovery pipeline under `research_gap_agent/`. It treats the user's research project as a technology baseline, discovers academic literature, extracts **evidence-backed research gaps**, maps those gaps to demonstrated project capabilities, resolves researchers and public institutional contacts, and creates a human-review queue for internship/co-authorship outreach.

The baseline is **Non-Destructive Differential Optical Colorimetry for Comparative Pungency Classification of Onion Layers**. The technology specification records non-destructive smartphone colorimetry, CIELAB/ΔE, segmentation, portability, low-cost operation, rapid analysis, and biochemical-gradient correlation. Its reported validation metrics are preserved as project evidence rather than silently replaced by assumptions. fileciteturn26file0

### Research-gap pipeline

`technology_spec.yaml` → OpenAlex discovery → gap-evidence extraction → capability matching → experimental bridge → researcher aggregation → public institutional contact verification → personalized pitch/email drafts → **human approval**.

The scoring rules explicitly reject title/keyword-only matches and candidates without an identifiable research gap or meaningful capability match. fileciteturn29file0

### Current implementation

- `research_gap_agent/cli.py` — OpenAlex discovery, abstract reconstruction, SQLite persistence and conservative first-pass scoring. fileciteturn28file0
- `research_gap_agent/gap_engine.py` — evidence-oriented gap sentence extraction and capability/experimental-bridge scoring.
- `research_gap_agent/contacts.py` — institutional-email validation helpers; never guesses an email.
- `research_gap_agent/outreach.py` — personalized research pitch/email generation with review fields.
- `research_gap_agent/tests/test_gap_engine.py` — regression tests for gap extraction and capability matching.
- `.github/workflows/research_gap_scan.yml` — weekly/manual discovery workflow; it uploads a SQLite review artifact and does not send outreach. fileciteturn19file0

The technology baseline is configured in `research_gap_agent/config/technology_spec.yaml`; the current scoring weights are in `research_gap_agent/config/scoring.yaml`. fileciteturn26file0 fileciteturn29file0

### Important limitation of the current stage

The first CLI pass still works primarily from title + abstract metadata. The new gap engine is the next layer, but **full-text evidence retrieval, researcher-level aggregation, and live institutional-page contact verification must be completed before a candidate is considered outreach-ready**. This prevents the system from pretending that keyword matches are genuine research gaps.

## Existing jobhunt agent

Run the existing application-search workflow as documented below.

```bash
python -m jobhunt run --mock --scorer keyword
```

The research-gap scan can be run with:

```bash
python -m research_gap_agent.cli scan --config research_gap_agent/config/technology_spec.yaml
```
