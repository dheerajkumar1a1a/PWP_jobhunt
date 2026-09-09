# $0 Research-Gap Internship Discovery Agent

A **free-first, research-gap-driven internship discovery pipeline** built inside `PWP_jobhunt`.

The system treats a user's research project as a **technology baseline**, searches the academic literature, looks for explicit or strongly evidenced methodological limitations, maps those limitations to the baseline's capabilities, ranks researchers rather than merely ranking papers, enriches candidates with public professional information, generates human-reviewable internship/co-authorship outreach drafts, and tracks important events in Telegram.

> **Core principle:** the system should find researchers for whom the project represents a credible solution or extension to a real research limitation. It is not intended to be a generic keyword-based professor-emailing bot.

> **Outreach rule:** discovery, scoring, enrichment, and drafting can be automated. Researcher outreach is **not automatically sent** by this pipeline. Human review remains required.

---

## 1. What this project is trying to automate

The target end-to-end workflow is:

```text
Your research project / technology baseline
                |
                v
       Search-query generation
                |
                v
  Academic discovery across free sources
  OpenAlex / Crossref / Semantic Scholar
                |
                v
       Deduplicate scholarly works
                |
                v
       Metadata + abstract scoring
                |
                v
  Explicit research-gap / limitation detection
                |
                v
   Capability-to-gap matching
                |
                v
 Public full-text discovery where exposed
                |
                v
   Deeper evidence-based rescoring
                |
                v
        Researcher aggregation
                |
                v
     Public profile/contact enrichment
                |
                v
   Internship/co-authorship draft generation
                |
                v
       Human review queue
          /             \
         v               v
     GitHub report     Telegram
                         |
                         v
              Candidate + email draft
```

The intended final experience is that a strong candidate arrives in Telegram together with a paper-specific outreach draft that can be reviewed before use.

---

## 2. Current technology baseline

The active project specification is stored in:

`research_gap_agent/config/technology_spec.yaml`

Current project name:

**Non-Destructive Differential Optical Colorimetry for Comparative Pungency Classification of Onion Layers**

Current objective:

**Use smartphone optical measurements to classify comparative onion-layer pungency without destroying the sample.**

The configured capability set includes:

- non-destructive measurement
- smartphone-based measurement
- low-cost architecture
- portability
- lightweight/small footprint
- fixed sample distance
- image segmentation
- irregular-object segmentation
- CPU-only processing
- static image processing
- sub-second analysis target
- CIELAB analysis
- differential colorimetry
- Delta-E (`ΔE`)
- biochemical-gradient correlation
- comparative classification
- agricultural/food application

Configured validation evidence includes:

- absolute CIELAB `R²` values: `L = 0.9907`, `a = 0.9959`, `b = 0.9912`
- differential colorimetry `R² = 0.9971`
- pyruvate range: `2.20–3.80 µmol/g`
- calibration `R² = 0.8977`
- segmentation threshold: `174.900`

The technology baseline is intentionally represented as structured capabilities instead of being reduced to the project title.

---

## 3. Academic discovery layer

### OpenAlex

OpenAlex is the primary high-volume scholarly metadata source in the current scanner.

The scanner is designed to tolerate transient `429`, `500`, `502`, `503`, and `504` responses using bounded retries/backoff. A temporary failure does not have to terminate the entire scan.

### Crossref

Crossref is used as a free metadata fallback/source for additional discovery.

### Semantic Scholar

Semantic Scholar is included as another free scholarly discovery source and can provide abstracts, authors, citation counts, DOI identifiers, and open-access PDF metadata when available.

### Deduplication

Results are deduplicated using DOI/identifier/title-derived keys before paper records are persisted.

### Respectful API behavior

The scanner uses bounded request sizes and delays between provider calls. Provider terms, rate limits, and availability still apply. The system does not attempt to bypass rate limits.

---

## 4. Research-gap engine

Core file:

`research_gap_agent/gap_engine.py`

The gap engine is deliberately more restrictive than ordinary semantic keyword matching.

It looks for evidence associated with limitations such as:

- destructive sampling
- laboratory dependence
- slow/time-consuming methods
- manual/operator-dependent analysis
- expensive or specialized instrumentation
- non-portable workflows
- imaging/computer-vision constraints
- explicit limitation/future-work statements

It then maps evidence against configured project capabilities such as:

- `non_destructive`
- `smartphone_based`
- `portable`
- `image_segmentation`
- `differential_colorimetry`
- `delta_e`
- `biochemical_gradient_correlation`
- `comparative_classification`

The scoring model includes separate concepts for:

- research-gap strength
- capability match
- experimental bridge
- application value

A paper should not be considered a serious target merely because its title contains similar words.

### Suggested interpretation of scores

| Score | Interpretation |
|---|---|
| 80–100 | Priority target; manual verification strongly recommended |
| 65–79 | Promising; inspect paper/full text and researcher/lab |
| 50–64 | Exploratory only |
| `<50` | Reject from the outreach queue |

The active configuration also defines a minimum target score of `70` and a priority threshold of `80` unless overridden by scoring configuration.

---

## 5. Full-text analysis

Core file:

`research_gap_agent/fulltext.py`

The system can perform a deeper pass when a public PDF/HTML location is explicitly exposed by scholarly metadata.

Supported processing includes:

- public PDF retrieval
- HTML text extraction
- PDF text extraction through `pypdf` when available
- sentence-level limitation/gap evidence extraction

The system does **not** bypass paywalls or use credentials to defeat access controls.

The deep pass is bounded so that a scheduled GitHub Actions run does not attempt to fetch unlimited full texts.

Each analyzed record can retain:

- public full-text URL
- full-text status
- full-text gap sentences
- rescored gap evidence

---

## 6. Researcher-level aggregation

Core file:

`research_gap_agent/researchers.py`

The system is designed to move from:

```text
Paper A -> Researcher X
Paper B -> Researcher X
Paper C -> Researcher X
```

to a researcher-level opportunity record.

This matters because a professor/lab with several related papers is potentially a stronger internship target than someone who authored a single loosely related paper.

Researcher records can carry:

- researcher name
- affiliations
- number of qualifying papers
- aggregate researcher score
- supporting papers
- evidence-backed gap records
- review status

---

## 7. Public author/contact enrichment

Core file:

`research_gap_agent/author_enrichment.py`

The intended rule is conservative:

```text
public professional information only
        |
        v
researcher identity/profile
        |
        v
affiliation / institution
        |
        v
public institutional email when explicitly available
```

The system should never fabricate or guess an email address.

A contact is considered useful for the outreach queue only when the available evidence supports the institutional relationship.

Contact records are persisted separately from drafts and remain `pending` for human review.

---

## 8. Internship/co-authorship draft generation

Core file:

`research_gap_agent/draft_builder.py`

The draft generator is designed around this chain:

```text
Their paper
    -> exact limitation
    -> your capability
    -> proposed experimental bridge
    -> possible research contribution
    -> internship / collaboration request
```

Supported output types include:

### Executive research pitch

A concise explanation of why the paper's limitation and the project's technology have a plausible research connection.

### Outreach email

A professional internship/co-authorship inquiry that references the target paper and the reported limitation.

All generated drafts remain `pending` for human review.

---

## 9. Telegram tracking

Core file:

`research_gap_agent/telegram.py`

Telegram is a **tracking and review channel**, not the automatic outreach channel.

The GitHub Action can report:

- papers scanned
- candidate count
- priority target count
- deep full-text count
- verified-contact count
- errors
- top researcher candidates

For candidates with drafts, Telegram can also show a copy-ready email message.

The email message supports an optional **Open Gmail Compose** link that pre-fills subject/body in Gmail without sending the message.

### Telegram secrets

Configure these as GitHub repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

The workflow checks for both values before attempting Telegram delivery. Secrets must not be committed to the repository.

---

## 10. OpenRouter free-model integration status

The GitHub Actions workflow currently exposes:

```text
OPENROUTER_API_KEY
OPENROUTER_ENABLED=true
```

The design target is to use OpenRouter's free-model route only for higher-value semantic reasoning rather than sending every discovered paper through an LLM.

The intended architecture is:

```text
large scholarly candidate set
        |
        v
cheap deterministic screening
        |
        v
small serious candidate set
        |
        v
OpenRouter free-model reasoning
        |
        v
structured gap assessment
        |
        v
high-confidence researcher targets
```

**Important implementation status:** the environment wiring exists, but the current main scan path is still primarily deterministic/rule-based. OpenRouter should be treated as an optional semantic-reasoning layer until an actual LLM invocation is present and verified in a successful GitHub Actions run.

This distinction is intentional: a configured secret is not evidence that an LLM call is actually taking place.

---

## 11. Gmail draft creation status

The project design includes direct Gmail draft creation as a desirable future output:

```text
validated researcher
        |
        v
personalized draft
        |
        v
Gmail `drafts.create`
        |
        v
appears directly in Gmail
        |
        v
human edits/reviews
        |
        v
human presses Send
```

### Current status

The current pipeline generates and stores outreach drafts and can expose a Gmail Compose URL from Telegram.

**Direct Gmail API draft creation is not yet treated as a completed production feature in this repository.** It should only be marked complete after Gmail OAuth, token storage, `drafts.create`, and a successful end-to-end test are implemented and verified.

This README intentionally distinguishes the implemented Compose-link experience from future mailbox-level draft creation.

---

## 12. SQLite state

The scan stores state in:

`data/research_gap.db`

The current schema includes tables for:

### `papers`

Stores scholarly paper identifiers, DOI, title, year, citations, score, gap JSON, author JSON, and raw metadata.

### `researcher_targets`

Stores aggregated researcher score, affiliations, paper count, supporting papers, and review status.

### `contacts`

Stores author/contact enrichment data, public email where found, verification URL, and review status.

### `drafts`

Stores the generated pitch/email and review status.

The schema is designed so later runs can retain a persistent audit trail rather than producing only ephemeral terminal output.

---

## 13. Research review report

Core file:

`research_gap_agent/review_report.py`

The Markdown review report can include:

- researcher ranking
- aggregate researcher score
- affiliations
- paper title
- paper score
- DOI
- discovery provider
- gap type
- mapped capability
- extracted evidence
- proposed experimental bridge
- evidence/capability/bridge strength
- review status

The report intentionally tells the reviewer to verify the original source before outreach.

Generated report:

`out/research_gap_report.md`

---

## 14. GitHub Actions automation

Workflow:

`.github/workflows/research_gap_scan.yml`

The workflow currently supports:

```yaml
workflow_dispatch:
```

for manual execution and a weekly scheduled run.

The weekly schedule currently runs at:

```text
06:17 UTC every Monday
```

The workflow performs:

1. repository checkout
2. Python 3.12 setup
3. dependency installation
4. unit tests
5. multi-source academic discovery
6. gap scoring
7. bounded public-full-text analysis
8. researcher aggregation
9. contact enrichment
10. draft generation
11. Markdown/SQLite artifact creation
12. Telegram tracking
13. upload of the review package

The workflow does **not** automatically send researcher emails.

---

## 15. GitHub Actions reliability work already implemented

The pipeline has already encountered and addressed two classes of CI failure.

### Python package import failure

The initial workflow could not import `research_gap_agent` during pytest collection.

The workflow was corrected to use the repository root as `PYTHONPATH` and run tests using:

```bash
python -m pytest research_gap_agent/tests -q
```

### Academic API instability

OpenAlex returned both `503 Service Unavailable` and `429 Too Many Requests` during earlier runs.

The scanner now uses:

- bounded retries
- exponential backoff
- `Retry-After` support
- provider failure tolerance
- Crossref/Semantic Scholar alternatives
- continuation to subsequent queries when one provider fails

This means a temporary provider outage should no longer automatically destroy the entire scheduled run.

A successful baseline GitHub Actions run has already been observed.

---

## 16. Unit tests

Tests live under:

`research_gap_agent/tests/`

The current test coverage includes the research-gap engine and review controls.

The gap-engine tests are intended to verify that:

- explicit limitation evidence is extracted
- unrelated papers do not become high-fit targets
- direct capability-gap relationships receive a meaningful score

Review tests verify the approval-state mechanics.

Run locally with:

```bash
python -m pytest research_gap_agent/tests -q
```

---

## 17. Local installation

Create an environment:

```bash
python -m venv .venv
```

Activate it.

### macOS/Linux

```bash
source .venv/bin/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run a scan:

```bash
python -m research_gap_agent.cli scan \
  --config research_gap_agent/config/technology_spec.yaml \
  --db data/research_gap.db \
  --report out/research_gap_report.md
```

---

## 18. Current repository components

The main research-gap implementation currently revolves around:

```text
research_gap_agent/
│
├── README.md
│
├── cli.py
├── gap_engine.py
├── scholarly.py
├── fulltext.py
├── researchers.py
├── author_enrichment.py
├── draft_builder.py
├── review.py
├── review_report.py
├── telegram.py
│
├── config/
│   ├── technology_spec.yaml
│   └── scoring.yaml
│
└── tests/
    ├── test_gap_engine.py
    └── test_review.py
```

Repository automation:

```text
.github/workflows/research_gap_scan.yml
```

Runtime state/output:

```text
data/research_gap.db
out/research_gap_report.md
```

---

## 19. Configuration

### Technology configuration

`research_gap_agent/config/technology_spec.yaml`

Defines:

- project name/objective
- capability set
- validation evidence
- search seeds
- safety/quality constraints

### Scoring configuration

`research_gap_agent/config/scoring.yaml`

Can provide threshold overrides for promising/priority targets.

The scanner also has safe defaults, so a missing scoring section should not crash a run.

---

## 20. Quality-control rules

The following rules are central to the design:

### Reject title-only matches

A similar title is not sufficient.

### Require explicit gap evidence

A target should have a limitation/challenge/future-work signal or equivalent strong evidence.

### Require capability-gap linkage

The project's technology must plausibly address the identified limitation.

### Prefer an experimental bridge

The system should be able to articulate a realistic validation experiment, not just say that two topics are related.

### Use public professional information only

No guessed private contact information.

### Keep outreach human-approved

The pipeline can prepare the work, but the human decides what is actually sent.

---

## 21. Telegram + Gmail usability goal

The desired user experience is:

```text
Telegram notification
        |
        +--> Candidate summary
        |
        +--> Paper + gap evidence
        |
        +--> Fit score
        |
        +--> Copy-ready email
        |
        +--> Open Gmail Compose
                    |
                    v
             User reviews/edits
                    |
                    v
               User sends
```

This is intentionally different from mass outreach automation.

---

## 22. What is complete vs. what remains

### Implemented

- project/technology baseline configuration
- structured capability matching
- deterministic gap extraction
- weighted paper scoring
- OpenAlex discovery
- Crossref discovery/fallback
- Semantic Scholar discovery
- result deduplication
- public full-text retrieval where exposed
- PDF/HTML extraction
- researcher aggregation
- public-contact enrichment framework
- draft generation
- SQLite persistence
- Markdown research report
- GitHub Actions scheduling/manual execution
- CI import/retry reliability fixes
- Telegram scan/candidate tracking
- Telegram copy-ready email output
- Gmail Compose URL support
- human-review statuses

### Partially implemented / being integrated

- OpenRouter free-model semantic reasoning: workflow key wiring exists, but the main scan is still deterministic until an actual LLM call is verified end-to-end.
- richer author profile resolution and institutional-page evidence
- stronger sentence-level evidence provenance
- stronger researcher continuity scoring

### Not yet production-complete

- direct Gmail API mailbox draft creation
- automatic sending of emails (intentionally excluded from the current design)
- a fully verified end-to-end OpenRouter reasoning run

---

## 23. Recommended future production pipeline

```text
                PROJECT BASELINE
                       |
                       v
              QUERY GENERATION
                       |
                       v
        +-------------------------------+
        | OpenAlex / Crossref / S2      |
        +---------------+---------------+
                        |
                        v
                  DEDUPLICATION
                        |
                        v
              METADATA PRE-FILTER
                        |
                        v
              PUBLIC FULL TEXT
                        |
                        v
          EVIDENCE-BACKED GAP EXTRACTION
                        |
                        v
              OPENROUTER FREE MODEL
                        |
                        v
            STRUCTURED GAP JUDGEMENT
                        |
                        v
              RESEARCHER AGGREGATION
                        |
                        v
             CONTACT VERIFICATION
                        |
                        v
              DRAFT GENERATION
                        |
              +---------+---------+
              |                   |
              v                   v
          GITHUB REPORT        TELEGRAM
                                  |
                                  v
                         HUMAN APPROVAL
                                  |
                                  v
                           GMAIL DRAFT
                                  |
                                  v
                           HUMAN SENDS
```

The architecture is deliberately **free-first** and designed to avoid unnecessary paid inference. Expensive semantic reasoning, when enabled, should be applied only to candidates that survive cheap screening.

---

## 24. Security and privacy notes

Never commit any of the following:

```text
TELEGRAM_BOT_TOKEN
OPENROUTER_API_KEY
GMAIL_CLIENT_SECRET
GMAIL_REFRESH_TOKEN
```

Store credentials in GitHub Actions Secrets or another secure secret store.

The repository should contain code and configuration, not private OAuth tokens.

---

## 25. Operational philosophy

This project is best understood as a **research opportunity discovery system** rather than an email automation script.

Its central question is:

> **Which researchers have a documented problem or limitation that this project can credibly help solve, and what specific experiment could turn that overlap into a research collaboration or internship?**

That question controls the search strategy, scoring, evidence requirements, outreach generation, and human-review gate.
