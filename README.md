<div align="center">

[![Career Agent](docs/readme-hero.svg)](docs/Final_Career_Agent_Overview.html)

# Career Agent

### Automate the search. Not the ambition.

**Upload your resume, tell Career Agent what you want, and use it to find, rank, and understand the jobs worth your attention.**

![Local-first](https://img.shields.io/badge/LOCAL--FIRST-76E8ED?style=for-the-badge&labelColor=0B1118&color=76E8ED)
![Open source](https://img.shields.io/badge/OPEN--SOURCE-AFA0F7?style=for-the-badge&labelColor=0B1118&color=AFA0F7)
![Human controlled](https://img.shields.io/badge/HUMAN--CONTROLLED-9BDFB7?style=for-the-badge&labelColor=0B1118&color=9BDFB7)

</div>

---

## What is Career Agent?

Job searching still involves a lot of repetitive work: checking career pages, opening dozens of roles, comparing requirements, remembering what you already looked at, and deciding which opportunities are actually worth your time.

Career Agent is being built to handle that repetitive layer for you.

You give it your **resume** and **career preferences**. It turns your experience into a structured profile, discovers job openings from supported public company sources, removes duplicates, checks your constraints, scores fit, and explains **why** a role may or may not be worth pursuing.

The goal is not to apply to everything.

The goal is to help you spend your attention on the right opportunities.

> **Career Agent recommends. You decide.** Application automation is experimental, optional, and disabled by default.

---

## The experience

```text
Upload resume
      ↓
Review your extracted experience
      ↓
Set roles, locations, compensation, work mode, and other preferences
      ↓
Find Jobs
      ↓
Discover → normalize → deduplicate → filter
      ↓
Deterministic fit + bounded AI analysis
      ↓
OpportunityScore + evidence + gaps
      ↓
Jobs worth your attention
      ↓
Save, research, prepare, or skip
```

Instead of showing another giant job feed, Career Agent is designed to answer four questions:

1. **Is this role actually relevant to me?**
2. **What evidence from my experience supports the match?**
3. **What is genuinely missing or still unclear?**
4. **What should I do next?**

---

## Why the matching is different

Career Agent does not treat a resume as a bag of keywords.

It keeps a structured record of the candidate's real experience and connects job requirements back to supporting evidence. It also keeps different kinds of gaps separate:

- an actual experience gap,
- an evidence or wording gap,
- or something the job posting simply does not make clear.

Your real-world constraints matter too. Location, work arrangement, compensation, seniority, relocation, employment type, work authorization, and sponsorship preferences can change the recommendation even when the technical match is strong.

The final score is an **opportunity-ranking signal**, not a prediction of whether a company will hire you.

---

## Current checkpoint

This private repository is a **P1 browser-test checkpoint**, not the final public release.

### Working now

| Capability | Status |
|---|---|
| Resume upload: PDF, DOCX, TXT | Working |
| AI-assisted profile and evidence extraction | Working, with one real-world extraction edge case being hardened |
| Human review and editing before approval | Working |
| Career preferences and constraints | Working |
| Public company-source ingestion | Working |
| Job normalization and deduplication | Working |
| Deterministic fit scoring | Working |
| Bounded semantic/AI fit analysis | Working |
| Constraint-aware recommendations | Working |
| OpportunityScore and global ranking | Working |
| Ranked dashboard and job detail analysis | Working |
| Saved opportunities and supporting research flows | Working |

### Being finished before the public release

- reliable retry/error handling for the resume-extraction edge case found during browser testing,
- a true fresh-user/reset experience with no leftover development state,
- zero-config **diversified multi-company discovery** so Find Jobs does not depend on manually choosing a company first,
- final browser validation of the complete new-user journey.

### Experimental

Application preparation and ATS browser automation are intentionally secondary. They remain human-reviewed and disabled by default.

```text
APPLICATION_MODE=manual
AUTO_SUBMIT_ENABLED=false
```

Career Agent never needs automatic submission in order to deliver its core value.

---

## Product overview

The repository includes a full interactive product concept with the intended experience, architecture diagrams, evidence-matching examples, opportunity views, and roadmap.

### [Open the Career Agent product overview →](docs/Final_Career_Agent_Overview.html)

The overview uses **fictional companies and sample data**. GitHub displays repository HTML as a file rather than running it as a website; for the full interactive version, download `docs/Final_Career_Agent_Overview.html` and open it in a browser.

The image at the top of this README links to the same overview.

---

## How Find Jobs works

Career Agent separates cheap, deterministic work from expensive AI analysis.

```text
public job sources
      ↓
normalize + deduplicate
      ↓
constraints + deterministic fit
      ↓
rank promising candidates
      ↓
bounded semantic analysis
      ↓
OpportunityScore
      ↓
ranked recommendations
```

The system does **not** send every discovered job to an LLM. Only a bounded, higher-priority subset is eligible for semantic analysis.

Current default:

```text
LLM_MAX_SEMANTIC_ANALYSES_PER_SCAN=10
```

When semantic fit is available, OpportunityScore combines deterministic and semantic fit and then applies freshness. If AI analysis is unavailable or fails, the job can still be ranked from deterministic signals rather than being automatically penalized.

---

## Quick start

### 1. Configure the backend

```powershell
Copy-Item backend/.env.example backend/.env
```

Configure a supported LLM provider if you want AI resume extraction and semantic analysis. Keep API keys only in environment variables.

### 2. Start Career Agent

```bash
docker compose up -d --build
```

### 3. Open onboarding

```text
http://localhost:3000/onboarding
```

Upload a PDF, DOCX, or TXT resume, review the extracted profile, set your preferences, and approve it before using the job-intelligence workflow.

---

## Local-first and private by design

Candidate-generated files are kept out of Git history. Real resumes, profiles, evidence, preferences, application artifacts, screenshots, and other private runtime state should remain ignored.

Tracked examples and automated-test fixtures must be fictional.

"Local-first" does **not** mean every operation is offline. If you configure a hosted AI provider, the content needed for that AI request is sent to that provider.

This project currently has no built-in multi-user authentication layer. Do not expose a local instance publicly without adding the appropriate security boundary.

See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).

---

## Architecture

The current stack is intentionally straightforward:

- **Next.js + React** — onboarding and the opportunity workspace
- **FastAPI** — API and orchestration
- **PostgreSQL** — jobs, analyses, research, and durable task state
- **Worker + scheduler** — discovery and background career-intelligence runs
- **LLM service abstraction** — structured resume extraction, semantic fit, research, and drafting where enabled
- **Playwright** — browser/UI regression testing and experimental ATS workflows

For the deeper component view, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Supported job-source direction

Career Agent uses adapters for public career systems rather than trying to scrape the entire web blindly.

Current source support includes:

| Source type | Discovery |
|---|---|
| Greenhouse | Supported |
| Ashby | Supported |
| Lever | Supported |
| SmartRecruiters | Supported |
| Workday | Supported / site-dependent |
| Generic public career pages | Best effort |
| Manually supplied career URL | Supported |

The next discovery pass focuses on using these adapters across a diversified starter universe of employers so a new user can click **Find Jobs** without first knowing which companies to add.

---

## Safety philosophy

Career Agent is intentionally conservative around applications:

- no CAPTCHA bypass,
- no access-control bypass,
- no authenticated LinkedIn automation,
- no fabricated candidate experience,
- no silent submission retries after an uncertain external submission state,
- no automatic submission by default.

Fit determines **priority**, not permission.

---

## Development

Backend:

```bash
cd backend
python -m pytest -q
python -m compileall -q app tests
```

Frontend:

```bash
cd frontend
npm install
npm run lint
npm run build
```

---

## Roadmap

Near-term work is focused on making the core promise boringly reliable:

**Resume → Preferences → Find Jobs → Analyze → Rank → Explain → Decide**

After that, the broader roadmap includes contact intelligence from verified public sources, posting-change intelligence, richer market insights, more source adapters, local-model support, and carefully controlled application workflows.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

Never commit real candidate information, API keys, live application payloads, private screenshots, or other personal runtime data.

---

## License

Licensed under the [Apache License 2.0](LICENSE).
