# Personalized JobSpy + Telegram Setup

This branch adds JobSpy as a multi-board discovery layer to `PWP_jobhunt` and keeps the existing LLM scoring, dedupe and Telegram pipeline.

## What is personalized

The initial profile is based on the public project evidence visible in the candidate's GitHub portfolio. It emphasizes:

- Data analysis / data science
- Machine learning
- Computer vision and YOLO/object detection/tracking
- Time-series forecasting
- AI/LLM applications
- AI/automation engineering
- Python development
- Research / analytics roles

The configured search locations prioritize Bengaluru, Hyderabad, Pune, Delhi NCR, Mumbai and remote India. The deterministic gate removes senior/staff/lead/manager roles, internships, sales/support/recruiting and unrelated software/platform roles before LLM scoring.

The current threshold is `7.5/10`, and Telegram sends the top 7 scored jobs from each successful run.

## JobSpy coverage

The adapter uses the current Python JobSpy site identifiers configured in `config.yaml`:

`linkedin`, `indeed`, `glassdoor`, `google`, `zip_recruiter`, `bayt`, `bdjobs`.

Naukri is intentionally not listed as a native Python JobSpy site. Do not add `naukri` to `site_name` and assume it will work; use a dedicated Naukri adapter/port when you specifically need native Naukri scraping.

## Telegram secrets

The workflow already expects these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` (or credentials required by your selected LLM provider)

To create the bot, open Telegram, start a conversation with **@BotFather**, create a bot with `/newbot`, then send one message to that bot. The chat ID must be the destination chat where alerts should arrive.

The existing notifier sends a compact HTML message with the best jobs and then the full HTML digest as a Telegram document.

## Exact resume personalization

The committed `profile.github_seed.json` is deliberately conservative: years of experience, education and seniority are unknown rather than guessed.

For exact ranking, run:

```bash
python -m jobhunt profile --resume path/to/your_resume.pdf --out profile.json
```

Then put the resulting JSON into the GitHub Actions `PROFILE_JSON` secret. The workflow automatically prefers that secret; otherwise it falls back to `profile.github_seed.json`.

## Local run

```bash
pip install -r requirements.txt
python -m jobhunt run --limit 50
```

For a no-network plumbing check:

```bash
python -m jobhunt run --mock --scorer keyword
```

The keyword scorer is only a development stub; use the LLM scorer for real relevance decisions.

## Schedule

`.github/workflows/daily.yml` runs at **06:00 IST on weekdays** and sends Telegram after the discovery, dedupe and LLM-ranking stages complete. `workflow_dispatch` can be used to run it manually.
