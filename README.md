# PWP_jobhunt — Job Search + Research-Gap Internship Automation

This repository contains two related automation systems:

1. **`jobhunt/`** — a personal job-search agent that discovers postings from public ATS APIs, deterministically filters/deduplicates them, optionally scores/drafts applications with an LLM, builds an HTML digest, tracks applications, and optionally emails the digest. It never submits an application.
2. **`research_gap_agent/`** — a free-first academic research-opportunity agent that treats a research project as a technology baseline, discovers scholarly papers, extracts evidence of methodological gaps, maps gaps to demonstrated capabilities, ranks researchers, enriches public contact information, creates internship/co-authorship drafts, and tracks results through Telegram. It is designed to require human approval before researcher outreach.

---

## 1. High-level architecture

```text
JOBHUNT
resume → profile → public ATS boards → normalize jobs → deterministic prefilter
       → dedupe → LLM screen → shortlist → LLM application kit → HTML digest
       → optional SMTP digest → application tracker

RESEARCH-GAP INTERNSHIP AGENT
technology baseline → query generation → OpenAlex/Crossref/Semantic Scholar
       → dedupe → evidence-first gap extraction → capability match
       → public full-text analysis → researcher aggregation
       → public-contact enrichment → internship research pitch/email
       → Telegram tracking → human review
```

The repository intentionally keeps **discovery, reasoning, drafting and sending as separate stages**. This makes failures observable and prevents a model or upstream API from silently turning a weak match into an outreach action.

---

# Part A — `jobhunt/`

## 2. Mathematical model of the job-search pipeline

For a posting \(j\), the deterministic prefilter can be viewed as a Boolean gate:

\[
P(j)=T(j)\land L(j)\land A(j),
\]

where:

- \(T(j)\) = title include/exclude condition,
- \(L(j)\) = location/remote condition,
- \(A(j)\) = freshness condition.

Only jobs satisfying \(P(j)=1\) survive to the LLM screening stage.

The LLM screening score is defined conceptually on a 0–10 scale:

\[
S_{LLM}(j)\in[0,10].
\]

The shortlist is:

\[
\mathcal{S}=\{j:P(j)=1\;\land\;S_{LLM}(j)\ge \tau\},
\]

where the configured threshold is `score_threshold` (default 7.0).

The top-\(N\) shortlist is:

\[
\operatorname{TopN}(\mathcal{S},N),
\]

with `max_per_digest` controlling \(N\).

For the offline keyword stub, the code uses a simple overlap fraction:

\[
O(j)=\frac{|K\cap W_j|}{\max(|K|,1)},
\]

where \(K\) is the candidate skill set and \(W_j\) is the token set represented by the posting. The score is approximately:

\[
S_{kw}(j)=\min(10,12O(j)+B(j)),
\]

where \(B(j)=2.5\) when a target title is found in the job title and \(0\) otherwise. This is explicitly a **development stub**, not a semantic matcher.

### LLM screening batch complexity

If \(n\) jobs survive deterministic filtering and the batch size is \(b\), the number of screen calls is:

\[
C_{screen}=\left\lceil\frac{n}{b}\right\rceil.
\]

The code defaults to `batch_size=8`, so 40 jobs require at most 5 screen calls.

### LLM drafting complexity

The rich application kit is generated one job at a time for the shortlist. Therefore:

\[
C_{draft}=|\mathcal{S}_{topN}|.
\]

This deliberately creates a lopsided cost structure: many cheap screens, few expensive drafts.

---

## 3. `jobhunt/__init__.py`

Defines package metadata:

```python
__version__ = "1.0.0"
```

There is no mathematical logic here. It exists so the package has a stable version identifier.

---

## 4. `jobhunt/__main__.py`

Contains the module entry point:

```python
from .cli import main
sys.exit(main())
```

This is what makes:

```bash
python -m jobhunt ...
```

work. `main()` returns a process exit status and `sys.exit()` passes it to the operating system.

---

## 5. `jobhunt/cli.py` — orchestration layer

This file coordinates the entire job-search pipeline.

### Environment loading

`_load_env()` implements a minimal `.env` reader without requiring `python-dotenv`. Each non-comment line of the form:

```text
KEY=VALUE
```

is inserted into `os.environ` only when that key is not already defined.

### Configuration loading

`_cfg()` reads YAML into a Python dictionary and fails early when the requested file does not exist.

### Profile loading

`_load_profile()` prefers the configured `profile.json`. During a mock/dry run it can fall back to `profile.example.json`.

### `cmd_profile()`

Pipeline:

```text
resume.pdf/.txt/.md
      ↓
LLM provider resolution
      ↓
structured profile JSON
      ↓
profile.json
```

The resulting profile contains fields such as skills, domains, projects, education, target titles and seniority.

### `cmd_run()`

The five major phases are:

1. **Fetch** — `fetch_all()` or `fetch_all_mock()`.
2. **Filter** — `prefilter()` then `Store.unseen()`.
3. **Screen** — keyword stub or LLM.
4. **Draft** — rich LLM application kit for the shortlist.
5. **Digest** — HTML output and optional SMTP email.

A crucial failure rule is implemented after LLM screening: if every LLM screening batch fails, the run aborts **before recording the jobs as seen**. This prevents a provider outage from permanently hiding jobs on later runs.

`cmd_applied()` marks a specific posting as applied.

`cmd_stats()` prints tracker statistics and exports CSV.

---

## 6. `jobhunt/fetch.py` — public ATS ingestion

The file defines the core `Job` dataclass:

```python
@dataclass
class Job:
    job_id: str
    ats: str
    company: str
    title: str
    location: str
    url: str
    description: str
    posted_at: str | None = None
    salary: str | None = None
    score: float | None = None
    reason: str | None = None
    draft: dict[str, Any] = field(default_factory=dict)
```

### Normalization

Three ATS adapters are implemented:

- `parse_greenhouse()`
- `parse_lever()`
- `parse_ashby()`

All adapters convert provider-specific JSON into the same `Job` representation. This is the key architectural abstraction: downstream filtering/LLM logic never has to understand each ATS schema.

### Stable job IDs

IDs are constructed as:

\[
ID=j_{ats}:j_{slug}:j_{provider\_id}.
\]

This creates a stable key for deduplication and tracking.

### HTML normalization

`strip_html()` removes markup while preserving useful line breaks for block elements. Mathematically, this is simply a text normalization function:

\[
f:\text{HTML string}\rightarrow\text{plain-text string}.
\]

### Network behavior

`fetch_board()` returns an empty list rather than crashing on a failed board. Therefore a dead company board does not destroy the whole run.

`fetch_all()` uses one `requests.Session()` and sleeps briefly between boards to reduce request pressure.

---

## 7. `jobhunt/prefilter.py` — deterministic cost-control gate

This file deliberately runs **before any LLM call**.

### Title filter

Include patterns are required; exclude patterns disqualify a job. Formally:

\[
T(j)=\left(\exists p\in I:p\text{ matches title}\right)\land\neg\left(\exists q\in E:q\text{ matches title}\right).
\]

### Location filter

The code checks the concatenated title/location text. A job passes if it contains an allowed location or an accepted remote hint.

### Freshness filter

If `max_age_days=m`, the cutoff is:

\[
t_{cutoff}=t_{now}-m\cdot 24\text{ hours}.
\]

A posting with a valid `posted_at` earlier than that cutoff is rejected.

### Date parsing

The parser accepts ISO-style dates, `YYYY-MM-DD`, and an ISO timestamp. Timezone-naive values are interpreted as UTC.

The final filter is:

\[
P(j)=T(j)\land L(j)\land A(j).
\]

Because this stage is deterministic, it costs no LLM tokens and is reproducible.

---

## 8. `jobhunt/llm.py` — profile, screen, draft

This is the semantic reasoning layer for the original jobhunt agent.

### JSON parsing

`parse_json()` is intentionally tolerant. It first attempts strict JSON, then searches for an outermost `[...]` or `{...}` span. This handles model replies wrapped in Markdown fences or short preambles.

### Profile extraction

`build_profile()` converts a resume into a structured object. The PDF branch uses `complete_document()` for providers that support native document input; otherwise the user can use text/Markdown.

### Screening prompt

The scoring rubric explicitly treats wrong seniority and hard requirement misses as major negatives. The instruction "most postings are a 4" prevents the model from inflating every score.

### Draft prompt

The application kit contains:

- `fit_summary`
- `tailored_bullets`
- `gaps`
- `cover_note`
- `questions_to_ask`

The hard rule is **never invent experience**. Unsupported claims must be listed as gaps.

### Output ceilings

The code defines separate token ceilings because reasoning models can consume output budget before visible text begins:

- `SCREEN_MAX_TOKENS = 4000`
- `DRAFT_MAX_TOKENS = 8000`
- `PROFILE_MAX_TOKENS = 4000`

### Keyword fallback mathematics

For the offline development stub:

\[
O(j)=\frac{|K\cap W_j|}{\max(|K|,1)},
\]

then:

\[
S_{kw}(j)=\min(10,12O(j)+2.5\cdot I_{title}),
\]

where \(I_{title}\in\{0,1\}\). This is intentionally crude and must not be treated as semantic judgment.

---

## 9. `jobhunt/providers.py` — provider abstraction

The `Provider` class defines a minimal interface:

```text
complete(system, user) -> text
complete_document(prompt, pdf) -> text
```

Implemented providers are:

- Anthropic
- Gemini
- Groq
- generic OpenAI-compatible endpoint
- Ollama

The provider layer does **not** know what a `Job` is and does not parse JSON. That separation lives in `llm.py`.

### Provider resolution

Precedence:

\[
\text{stage-specific env} > \text{global env} > \text{built-in default}.
\]

For example, `SCREEN_PROVIDER` overrides `LLM_PROVIDER` for screening.

### Preflight

Missing API credentials fail before the first batch. This avoids the bad failure mode where 40 batches all fail with the same authentication error.

### OpenAI-compatible abstraction

The same class can talk to providers that implement `/chat/completions`, with a configurable base URL.

### Ollama

Ollama uses the local HTTP API. This gives a no-key, no-provider-billing path when a model is installed locally. Its real constraint is local compute.

---

## 10. `jobhunt/digest.py` — HTML report rendering

This file generates the daily HTML email.

It uses inline CSS because Gmail may remove `<style>` blocks.

Each job becomes a visual card with:

- title
- score badge
- company/location/ATS
- fit summary
- tailored bullets
- honest gaps
- cover note
- questions
- application link

The score badge has piecewise thresholds:

\[
Color(s)=
\begin{cases}
\text{high}, & s\ge 8.5\\
\text{medium}, & 7\le s<8.5\\
\text{low}, & s<7
\end{cases}
\]

The actual implementation uses CSS color values, while this README refers to them abstractly as high/medium/low to describe the logic.

The subject is:

\[
subject = f(|J|, date),
\]

where \(|J|\) is the number of shortlisted jobs.

---

## 11. `jobhunt/mailer.py` — SMTP delivery

The mailer builds a multipart email containing:

- plain-text fallback
- HTML alternative

SMTP is configured through environment variables. Gmail is expected to use an App Password rather than the normal account password.

The important safety distinction is that this mailer sends the **daily digest to the user**, not job applications to employers.

---

## 12. `jobhunt/store.py` — dedupe and application tracking

`seen.json` acts as both:

1. a dedupe index
2. an application-state store

`unseen()` implements:

\[
U=J\setminus Seen.
\]

`record()` creates a persistent entry with `first_seen`, score, URL, email state and application state.

`mark_applied()` changes:

```text
applied = False → True
```

and records the UTC timestamp.

`stats()` returns:

- tracked
- emailed
- applied

`export_csv()` creates an audit-friendly tracker with stable columns.

---

## 13. `jobhunt/mock.py` — deterministic fixture system

Mock data exercises the **real ATS parsers**, not a fake internal data model.

Fixtures deliberately include:

- correct role/city/freshness
- wrong seniority
- wrong discipline
- wrong city
- stale posting
- an unlisted Ashby draft

Dates are computed relative to the current time so examples do not silently become stale.

The Lever fixture intentionally stores milliseconds since epoch. Dividing by 1000 before converting to a UTC date prevents the classic "1970" parsing bug.

---

# Part B — `research_gap_agent/`

## 14. Research objective and mathematical representation

The research-gap system models the user's project as a set of demonstrated capabilities:

\[
C=\{c_1,c_2,\ldots,c_m\}.
\]

For example:

- non-destructive operation
- smartphone-based measurement
- low cost
- portability
- fixed sample distance
- image segmentation
- irregular object segmentation
- CPU-only processing
- differential colorimetry
- CIELAB/ΔE
- biochemical-gradient correlation
- comparative classification

The configured technology baseline records these capabilities and project evidence. fileciteturn162file0L1-L2

For a paper \(p\), the system extracts a set of gap observations:

\[
G(p)=\{g_1,g_2,\ldots,g_k\}.
\]

The objective is to identify a strong mapping:

\[
g_i \longleftrightarrow c_j.
\]

A useful target is therefore not merely "paper similarity" but:

\[
Opportunity(p,c)=EvidenceGap(p)\times CapabilityCoverage(c)\times Bridge(p,c).
\]

The current implementation approximates these components with explicit heuristic strengths and a weighted score; OpenRouter/free is available as an AI reasoning layer but is not the only mechanism.

---

## 15. `research_gap_agent/__init__.py`

Package marker. It contains no domain mathematics.

---

## 16. `research_gap_agent/config/technology_spec.yaml` — project ontology

This is the **most important data file** because it states what the technology actually is.

The current project is:

> Non-Destructive Differential Optical Colorimetry for Comparative Pungency Classification of Onion Layers

The project objective is smartphone optical measurement for comparative onion-layer pungency classification without destroying the sample. The configuration also records validation values such as differential \(R^2=0.9971\), CIELAB-related validation values and the pyruvate range. fileciteturn162file0L1-L2

### Mathematical meaning of the stored \(R^2\)

The coefficient of determination can be written as:

\[
R^2=1-\frac{\sum_i(y_i-\hat y_i)^2}{\sum_i(y_i-\bar y)^2}.
\]

Thus larger \(R^2\) means smaller residual sum of squares relative to the total variance of the target.

The configuration's `delta_e` capability corresponds to color-difference analysis, commonly represented by a Euclidean distance in CIELAB for classical \(\Delta E_{ab}^*\):

\[
\Delta E_{ab}^*=\sqrt{(\Delta L^*)^2+(\Delta a^*)^2+(\Delta b^*)^2}.
\]

The repository does **not** claim that every historical ΔE variant is identical; the equation above is the classical form used to explain the mathematical concept.

---

## 17. `research_gap_agent/config/scoring.yaml` — opportunity scoring policy

The configured weights are: 

- gap evidence = 30
- capability coverage = 25
- experimental bridge = 20
- researcher ownership = 10
- application impact = 10
- contactability = 5. fileciteturn161file0L1-L2

If each component is normalized to \([0,1]\), the intended weighted score is:

\[
S=30E_g+25E_c+20E_b+10E_r+10E_a+5E_t.
\]

Because the weights sum to 100:

\[
0\le S\le100.
\]

Gap evidence rules are:

\[
E_g=\begin{cases}
1.0 & \text{explicit limitation}\\
0.9 & \text{future-work/need statement}\\
0.8 & \text{methodological constraint}\\
0.3 & \text{inferred only}\\
0.0 & \text{absent}
\end{cases}
\]

Capability coverage rules are:

\[
E_c=\begin{cases}
1.0 & \text{direct match}\\
0.6 & \text{plausible extension}\\
0.25 & \text{weak}
\end{cases}
\]

The hard-reject rules are deliberately strong: no identifiable gap, title/keyword-only similarity, no meaningful capability match, unresolved affiliation, or contact from a non-public/private source should not enter the real outreach queue. fileciteturn161file0L1-L2

Thresholds are currently:

- 80+ priority
- 65–79 promising
- 50–64 exploratory
- below 50 reject. fileciteturn161file0L1-L2

---

## 18. `research_gap_agent/gap_engine.py` — deterministic evidence and capability matcher

The central dataclass is `GapResult`, containing:

- `gap_type`
- `evidence`
- `capability`
- `bridge`
- gap strength
- capability strength
- bridge strength
- score

### Gap-pattern recognition

The code defines regular-expression families for:

- destructive methods
- laboratory dependence
- slow/laborious workflows
- manual/subjective operation
- expensive equipment
- non-portability
- imaging/computer vision
- colorimetry
- future work/limitations

### Capability recognition

The code maps project capabilities to patterns such as smartphone, non-destructive, portable, segmentation, CPU, CIELAB, ΔE, biochemical/pyruvate, classification, food/agriculture.

### Sentence splitting

`split_sentences()` approximates sentence boundaries with punctuation followed by whitespace.

### Evidence extraction

`extract_gap_evidence()` retains up to five sentences containing explicit limitation/future-work or methodological-constraint language.

### Score construction

For each evidence sentence, the implementation estimates:

\[
gap\_strength=\min(1,0.75+0.08n_g),
\]

\[
capability\_strength=\min(1,0.60+0.08n_c),
\]

\[
bridge\_strength=\min(1,0.55+0.10\min(n_g,n_c)),
\]

where \(n_g\) is the number of matched gap types and \(n_c\) the number of matched capabilities.

The implemented provisional score is approximately:

\[
S_{local}=35G+30C+15B+10A,
\]

where \(A=1.0\) for agriculture/classification alignment and \(0.4\) otherwise.

This code-level score is intentionally a local screening heuristic and is not identical to the more general 100-point policy in `config/scoring.yaml`.

### Why this distinction matters

The architecture separates:

```text
policy weights
vs.
current deterministic implementation
```

so later versions can make the actual scorer conform exactly to the policy.

---

## 19. `research_gap_agent/scholarly.py` — multi-source discovery

Three sources are implemented:

- OpenAlex
- Crossref
- Semantic Scholar

The user-agent string identifies the application and its respectful-rate/no-automated-outreach intent.

### Retry model

Transient status codes include:

\[
\{429,500,502,503,504\}.
\]

The retry delay is bounded by a small maximum. When `Retry-After` exists, it is respected up to the bound.

### Cross-source deduplication

Each result gets a deduplication key based primarily on DOI, otherwise ID/title.

The high-level effect is:

\[
P_{all}=P_{OA}\cup P_{CR}\cup P_{SS},
\]

followed by deduplication:

\[
P_{unique}=Unique(P_{all}).
\]

### Abstract reconstruction

OpenAlex exposes an inverted abstract index, which is reconstructed by ordering tokens by their recorded positions.

---

## 20. `research_gap_agent/fulltext.py` — public-text deep analysis

This module fetches only URLs that are explicitly public. It does not bypass paywalls.

### PDF extraction

If `pypdf` is available, pages are read and concatenated into text.

### HTML extraction

Scripts/styles/tags are removed and HTML entities are decoded.

### Gap sentence locator

`locate_gap_sentences()` finds sentences containing words such as limitation, challenge, future work, destructive, laborious, expensive, portable, smartphone or cannot.

This is a second-pass evidence collector; it is intentionally simpler than a full NLP discourse parser.

---

## 21. `research_gap_agent/researchers.py` — researcher aggregation

Papers are grouped by author name.

For a researcher with \(n\) qualifying papers, continuity is:

\[
C_r=\min\left(1,\frac{n}{3}\right).
\]

The current researcher score is:

\[
S_r=0.85S_{max}+10C_r,
\]

clipped at 100.

This means a researcher with multiple relevant papers gets an additional continuity component while the strongest linked paper remains dominant.

Affiliations are accumulated as a set and then sorted.

---

## 22. `research_gap_agent/author_enrichment.py` — author profile enrichment

`candidate_profile_urls()` collects already-known profile/orcid/homepage URLs.

`enrich_author()` passes those URLs to the public-profile resolver and adds:

- profile URL
- public email
- source
- verification flag

No address is invented.

---

## 23. `research_gap_agent/enrichment.py` — conservative public-contact verification

The module defines `ProfileCandidate`.

### Email extraction

A regular expression recognizes ordinary email syntax.

### Institutional validation

Personal/free domains such as Gmail, Yahoo, Outlook, Hotmail and Proton are rejected.

The conservative check then compares the email domain with the public profile's host:

\[
Verified=PublicPage\land NonFreeDomain\land DomainMatch.
\]

This is intentionally conservative and can produce false negatives. It is safer than guessing.

---

## 24. `research_gap_agent/contact_enricher.py` — alternate contact helper

This module is a more general page scanner that:

1. downloads a public HTML/text page,
2. extracts up to ten email candidates,
3. rejects obvious placeholder/no-reply addresses,
4. chooses a plausible institutional address.

The domain heuristic uses affiliation text and common academic-domain patterns such as `.edu`/`.ac.`.

It is less strict than `enrichment.py`, so production usage should prefer the stricter path unless the workflow explicitly documents otherwise.

---

## 25. `research_gap_agent/contacts.py` — verification primitives

This module contains:

- `ContactCandidate`
- `is_institutional_email()`
- `extract_public_emails()`
- `verify_candidate()`

It uses the same principle:

\[
ContactOK=ValidURL\land InstitutionalEmail.
\]

---

## 26. `research_gap_agent/drafts.py` — alternate template writer

`build_experiment()` turns a gap record into an experimental bridge.

`build_pitch()` produces a concise research pitch that references the paper evidence and the technology.

`build_email()` adds a subject, salutation and internship request.

This is a deterministic template path.

---

## 27. `research_gap_agent/draft_builder.py` — primary deterministic outreach builder

`proposed_experiment()` maps gap classes to a specific experiment.

Examples:

- destructive → compare non-destructive optical measurement with biochemical assay
- laboratory → benchmark portable workflow against reference method
- slow → compare end-to-end analysis time
- manual → compare automated segmentation/classification to expert labels
- expensive → cost/performance comparison
- nonportable → validate under field/near-field conditions

`build_pitch()` combines:

\[
PaperEvidence + GapType + Capability + ProposedExperiment.
\]

`build_email()` then wraps that pitch in a professional internship request.

The current implementation is deterministic; OpenRouter/free can be used as the higher-level reasoning layer when wired into the scan path.

---

## 28. `research_gap_agent/openrouter_free.py` — OpenRouter free-router client

This file defines:

```text
BASE_URL = https://openrouter.ai/api/v1/chat/completions
DEFAULT_MODEL = openrouter/free
```

The intent is to use OpenRouter's free router instead of hardcoding a paid model.

### `enabled()`

Returns true only when both:

- `OPENROUTER_API_KEY` exists
- `OPENROUTER_ENABLED` is truthy

### `chat()`

Sends a standard chat-completions payload with system/user messages, temperature and maximum output tokens.

### `analyze_gap()`

Requests structured JSON containing:

- gap statement
- evidence strength
- capability match
- bridge
- novelty rationale
- confidence
- reject flag

### `draft_email()`

Requests a concise paper-specific academic internship email based only on supplied facts.

### Important implementation status

The module is present and the GitHub Action exposes `OPENROUTER_API_KEY`/enables the feature, but the current `research_gap_agent/cli.py` still primarily uses the deterministic gap engine directly. Therefore this README treats OpenRouter as **available integration code, not a claim of fully verified end-to-end LLM usage in every scan**.

---

## 29. `research_gap_agent/cli.py` — research pipeline orchestrator

This file is the central coordinator.

### Database tables

SQLite currently creates:

#### `papers`

Stores paper ID, DOI, title, year, citations, score, gap JSON, author JSON and raw metadata.

#### `contacts`

Stores paper ID, author, affiliation, public email, verification URL and review status.

#### `drafts`

Stores paper ID, author, pitch, email and review status.

#### `researcher_targets`

Stores researcher name, affiliations, paper count, researcher score, linked papers and review status.

### Deep-analysis stage

For a candidate above the initial local threshold, the workflow can find a public PDF and run a second pass over up to a bounded number of characters.

This creates a two-stage information funnel:

\[
Metadata\rightarrow InitialScore\rightarrow PublicFullText\rightarrow DeepScore.
\]

The configured deep-analysis limit is 12.

### Draft/contact enrichment

For each researcher target, the code:

1. merges author records from linked papers,
2. enriches public profiles,
3. selects a verified public institutional email when available,
4. creates a pitch,
5. creates an email draft,
6. marks draft status as `pending`.

### Metrics exported to GitHub Actions

The scanner publishes:

- `RG_SCANNED`
- `RG_CANDIDATES`
- `RG_PRIORITY`
- `RG_ERRORS`
- `RG_DEEP_FULLTEXT`
- `RG_VERIFIED_CONTACTS`

These values feed the Telegram summary.

---

## 30. `research_gap_agent/review.py` — human approval gate

Valid statuses are:

```text
pending
approved
rejected
```

`approval_check()` blocks approval when:

- researcher score < 70
- no linked papers
- no verified public institutional email
- no contact verification URL
- no human approval

Mathematically, a target can pass only if:

\[
Approved=ScoreOK\land PaperOK\land EmailOK\land SourceOK\land HumanApproved.
\]

This is the most important safety boundary for outreach.

---

## 31. `research_gap_agent/review_report.py` — review artifact

The report renders, for every target:

- researcher score
- affiliations
- review status
- up to three linked papers
- paper score
- DOI
- provider
- gap type
- mapped capability
- evidence
- bridge
- gap/capability/bridge strengths
- executive pitch
- email draft

The report explicitly tells the reviewer to verify the original paper, exact limitation, author identity, affiliation, public contact and experiment before outreach. fileciteturn159file0L1-L2

---

## 32. `research_gap_agent/review_report.py` — output semantics

The artifact is Markdown, making it easy to inspect in GitHub or download from Actions.

The goal is not presentation polish; it is auditability. Every important generated claim remains visible beside its evidence fields.

---

## 33. `research_gap_agent/telegram.py` — tracking and copy-ready outreach

The Telegram module uses the official Bot API over HTTPS.

`send_message()` posts to `sendMessage`.

The configuration reads:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- optional `TELEGRAM_ENABLED`

### Candidate message

Contains:

- candidate name
- affiliation
- fit score
- paper
- gap evidence

### Email message

`format_email_draft()` generates:

- recipient display name
- subject
- body
- copy-subject button
- Gmail compose URL with prefilled subject/body

The Gmail compose URL is **not** a Gmail API send. It opens a compose page; the user still decides whether to send.

---

## 34. `research_gap_agent/tests/test_gap_engine.py`

Tests include:

1. explicit laborious/laboratory/future-work evidence is extracted,
2. an unrelated paper with a gap but no capability match scores zero,
3. a direct smartphone/non-destructive/portable match scores positively.

This is a minimal regression suite for the deterministic matcher.

---

## 35. `research_gap_agent/tests/test_review.py`

Tests include:

1. pending targets cannot pass approval,
2. a sufficiently scored target with paper/contact/source and `approved` status can pass,
3. an invalid review status raises `ValueError`.

These tests enforce the human-review boundary.

---

# Part C — GitHub Actions

## 36. `.github/workflows/research_gap_scan.yml`

The scheduled research workflow:

```text
checkout
→ setup Python 3.12
→ install dependencies
→ run unit tests
→ run research scan
→ notify Telegram
→ upload SQLite + Markdown report
```

The current schedule is weekly and the workflow also supports manual dispatch. The workflow passes `PYTHONPATH`, Telegram secrets and `OPENROUTER_API_KEY` into the runner. fileciteturn143file0L1-L2

### Telegram behavior

The workflow reads candidate targets from SQLite and sends Telegram summaries plus copy-ready outreach drafts. fileciteturn134file0L1-L2

### Safety behavior

The workflow never calls a researcher-email sending endpoint. It only creates/records drafts and sends tracking notifications.

---

# Part D — Current end-to-end research-gap flow

## 37. Exact data flow

```text
technology_spec.yaml
    │
    ├── project capabilities
    ├── validation evidence
    ├── query seeds
    └── safety constraints
           │
           ▼
    OpenAlex / Crossref / Semantic Scholar
           │
           ▼
       deduplicate
           │
           ▼
   title + abstract gap screen
           │
           ▼
       local score
           │
           ▼
   public PDF/HTML discovery
           │
           ▼
    deep full-text analysis
           │
           ▼
   researcher aggregation
           │
           ▼
 public profile enrichment
           │
           ▼
 verified public institutional contact
           │
           ▼
    internship pitch + email
           │
           ▼
       SQLite state
           │
           ├── GitHub Markdown report
           └── Telegram tracking
                    │
                    ▼
               HUMAN REVIEW
```

---

# Part E — Telegram workflow

## 38. What Telegram is for

Telegram is a **tracking and review interface**, not the outreach sender.

A useful candidate notification looks conceptually like:

```text
🔬 RESEARCH-GAP CANDIDATE

Researcher
Institution

Fit score: 91.4/100
Paper: ...

Why it matches:
...

📧 Copy-ready email is below.
```

Then the email message contains:

```text
📧 COPY-READY EMAIL

To: ...
Subject: ...

EMAIL BODY
...

[Copy Subject]
[Open Gmail Compose]
```

---

# Part F — Free-first / cost model

## 39. What is actually free

The architecture is designed so these layers can run without a paid LLM subscription:

- Python
- SQLite
- GitHub repository
- academic metadata APIs, subject to their published terms/rate limits
- deterministic regex/NLP scoring
- local Ollama inference when a local model is installed
- Telegram Bot API calls within Telegram's operational limits

OpenRouter's free router is an optional zero-price inference path, but its free model availability and provider limits can change.

The system therefore uses the principle:

\[
Cost\approx C_{metadata}+C_{compute}+C_{LLM\,calls}.
\]

The first two can often be near-zero in a personal deployment; paid LLM cost is avoidable when local inference or a free route is used.

The architecture should never be interpreted as "unlimited" because academic providers, GitHub Actions, Telegram and model providers all impose quotas/rate limits.

---

# Part G — Security and privacy

## 40. Secrets

Never commit:

```text
TELEGRAM_BOT_TOKEN
OPENROUTER_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
GROQ_API_KEY
SMTP_PASS
```

Store them in GitHub Actions Secrets or local environment configuration.

### Contact-data policy

The research-gap agent is deliberately conservative about researcher contact data:

- no guessed email addresses,
- no private contact sources,
- public institutional pages only,
- human verification before outreach.

---

# Part H — Failure handling

## 41. Research API failures

Transient HTTP failures trigger bounded retries.

A provider failure should reduce coverage, not destroy the whole run.

Conceptually:

\[
Result=\bigcup_{provider\in Providers}Successful(provider).
\]

The system can therefore operate with partial provider availability.

## 42. LLM failures

The jobhunt pipeline skips failed batches rather than crashing the whole run immediately, and it refuses to record everything as "seen" when no scores were successfully produced.

The research-gap pipeline retains deterministic fallback behavior even when an optional LLM integration is unavailable.

## 43. Full-text failures

A missing/unreadable public PDF does not invalidate the paper. It simply means the deeper evidence layer could not be completed.

---

# Part I — Testing and reproducibility

## 44. Local commands

### Jobhunt dry run

```bash
python -m jobhunt run --mock --scorer keyword
```

### Research-gap scan

```bash
python -m research_gap_agent.cli scan \
  --config research_gap_agent/config/technology_spec.yaml
```

### Tests

```bash
python -m pytest research_gap_agent/tests -q
```

The GitHub Action uses the same test command and explicitly sets the repository as `PYTHONPATH` so imports resolve under CI.

---

# Part J — Repository state and implementation notes

## 45. What is fully implemented

### Jobhunt

- public ATS discovery for Greenhouse/Lever/Ashby
- normalized `Job` model
- deterministic title/location/freshness filtering
- persistent dedupe/application tracker
- provider-agnostic LLM interface
- profile extraction
- batch screening
- per-job drafting
- HTML digest
- optional SMTP delivery
- mock fixtures

### Research-gap agent

- project capability ontology
- configurable search seeds
- OpenAlex/Crossref/Semantic Scholar discovery
- deduplication
- deterministic gap evidence extraction
- capability mapping
- researcher aggregation
- public-contact enrichment helpers
- SQLite persistence
- Markdown review report
- Telegram tracking
- copy-ready email and Gmail compose link
- OpenRouter/free integration module
- human-review gate
- GitHub Actions automation

---

## 46. What is partially implemented / should be hardened next

1. **OpenRouter/free should be wired into the live `cli.py` deep-analysis and email-generation stages** rather than being merely an available module.
2. The general policy score in `config/scoring.yaml` should be reconciled with the deterministic score formula in `gap_engine.py` so there is one canonical 0–100 scoring equation.
3. Researcher profile discovery can be expanded from already-known URLs to source-native author-profile endpoints while preserving conservative contact verification.
4. Gmail API `drafts.create` can be added for true mailbox drafts; the current Telegram path uses a Gmail compose URL and does not create a mailbox draft.
5. Telegram sending should surface API errors instead of swallowing all exceptions so invalid bot/chat credentials cannot look like successful runs.
6. Full-text evidence should record source locations/page numbers/sections where available, making generated claims easier to audit.

---

# Part K — Recommended target architecture

## 47. Final desired research-opportunity agent

```text
             YOUR TECHNOLOGY
                    │
                    ▼
             capability graph
                    │
                    ▼
        query generation + expansion
                    │
                    ▼
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   OpenAlex      Crossref   Semantic Scholar
       └────────────┼────────────┘
                    ▼
               deduplication
                    ▼
           cheap first-pass filter
                    ▼
             public full text
                    ▼
         OpenRouter / free LLM
                    ▼
         structured gap analysis
                    ▼
      gap ↔ capability ↔ experiment
                    ▼
            researcher ranking
                    ▼
          profile/contact verify
                    ▼
             draft proposal
                    ▼
              Gmail Draft
                    ▼
                Telegram
                    ▼
             HUMAN REVIEW
                    ▼
             user presses Send
```

The most important semantic requirement is preserved throughout:

> **Do not contact a researcher merely because the subject areas are similar. Contact them when their published work contains a defensible, evidence-backed limitation that the user's demonstrated technology could plausibly address with a concrete experiment.**

---

# Part L — Evidence and audit philosophy

## 48. Why this repository is designed this way

A high-quality research internship workflow needs traceability:

\[
Claim \rightarrow SourceEvidence \rightarrow Gap \rightarrow Capability \rightarrow Experiment \rightarrow Outreach.
\]

Breaking any link weakens the outreach case.

The repository therefore stores the intermediate objects instead of collapsing everything into a single opaque LLM answer.

That design supports three useful review questions:

1. **Did the paper actually say this?**
2. **Does the candidate actually possess this capability?**
3. **Is the proposed experiment scientifically plausible?**

Only when all three answers are satisfactory should a researcher outreach draft be treated as ready for a human to send.
