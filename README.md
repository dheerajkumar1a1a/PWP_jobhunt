# jobhunt

A personal job-search agent. It reads public ATS APIs every morning, filters and ranks roles, drafts an application kit, and emails a digest. **It never submits an application.**

## Research-gap internship discovery

This repository now also contains a free-first research internship discovery prototype under `research_gap_agent/`. It treats the user's research project as a technology baseline, discovers academic literature, looks for **evidence-backed research gaps**, maps those gaps to project capabilities, and creates a human-review queue for researcher outreach.

The initial baseline is **Non-Destructive Differential Optical Colorimetry for Comparative Pungency Classification of Onion Layers**. The agent encodes non-destructive smartphone colorimetry, CIELAB/ΔE, segmentation, portability, low-cost operation, rapid analysis, and biochemical-gradient correlation as capabilities. It deliberately rejects title-only matching and requires explicit gap evidence before a paper can become an outreach candidate.

### Research-gap pipeline

`technology_spec.yaml` → OpenAlex discovery → evidence scoring → capability matching → author/affiliation records → public-contact verification → personalized pitch/email drafts → human approval.

The first implementation is intentionally conservative: it does **not** automatically email researchers. Full-text gap extraction, public institutional email verification, richer author scoring, and optional local-LLM analysis are the next stages.

See `research_gap_agent/README.md` and `research_gap_agent/config/technology_spec.yaml`.

## Existing jobhunt agent

Run the existing application-search workflow as documented below.

```bash
python -m jobhunt run --mock --scorer keyword
```

The research-gap scan can be run with:

```bash
python -m research_gap_agent.cli scan --config research_gap_agent/config/technology_spec.yaml
```

The GitHub Actions workflow `.github/workflows/research_gap_scan.yml` runs weekly and supports manual dispatch. Results are uploaded as an artifact; no outreach is sent.
