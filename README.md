# Career Intelligence Agent

An open-source, local-first personal job-search agent that continuously discovers jobs worth your time, evaluates them against verified experience and configured constraints, explains the evidence behind each match, distinguishes real gaps from wording gaps, and recommends the next useful action.

Application preparation and ATS browser automation are preserved as an **experimental, optional subsystem**. Fit controls priority—not permission—and nothing submits unless the configured submission safeguards allow it.

> **Safety default:** `APPLICATION_MODE=manual` and `AUTO_SUBMIT_ENABLED=false`.

## Product tour

<!-- TODO: add public screenshots after sanitizing demo data. -->

- Landing and guided local onboarding
- “Jobs worth your attention” opportunity dashboard
- Evidence-grounded match reasons and typed gaps
- Constraint-aware recommendations: `APPLY_NOW`, `APPLY`, `CONTACT_FIRST`, `STRETCH`, `SKIP`
- Local market insights and saved-opportunity pipeline
- Company and role research with source citations
- Evidence-grounded application packages and tailored resumes
- Experimental Ashby/Greenhouse/Lever form inspection and controlled filling
- Durable submission state, receipts, duplicate protection, and uncertainty lockout

## How it works

```text
private profile + preferences
              ↓
public job discovery → normalize → deduplicate → classify
              ↓
deterministic + semantic fit → constraints → opportunity score
              ↓
evidence-backed explanation → gaps → recommended next action
              ↓
optional application preparation / experimental ATS automation
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for component boundaries.

## Quick start

1. Copy the environment template and configure an optional LLM provider:

   ```powershell
   Copy-Item backend/.env.example backend/.env
   ```

2. Start the stack:

   ```bash
   docker compose up -d --build
   ```

3. Open `http://localhost:3000/onboarding`, upload a PDF, DOCX, or TXT resume,
   review every extracted claim, configure job preferences, and approve. The
   application creates the ignored `profile.local.json`, `evidence.local.json`,
   and `preferences.local.json` files for you.

The project has no built-in authentication. Treat any public deployment accordingly and read [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).

## Configuration

The backend uses environment variables documented in `backend/.env.example`, including:

- `DATABASE_URL`
- `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`
- candidate `*_PATH` settings pointing to ignored local files
- `APPLICATION_MODE=manual`
- `AUTO_SUBMIT_ENABLED=false`

Tests use fictional fixtures and mock providers. No real API key is required.

## AI providers

Deterministic discovery and scoring work without an LLM. Optional semantic analysis, research, and application drafting support configured providers. OpenAI Structured Outputs are schema-constrained, bounded, and cost-tracked. Keep keys in environment variables only.

After onboarding, **Find Jobs** scans enabled public company sources in a background worker, scores every normalized job deterministically, and sends only the highest-priority bounded subset to semantic analysis. The default budget is `LLM_MAX_SEMANTIC_ANALYSES_PER_SCAN=10`. When semantic fit exists, OpportunityScore blends 45% deterministic fit with 55% semantic fit, then applies freshness; missing or failed AI analysis falls back to deterministic scoring without a penalty. The API globally ranks the complete result set before pagination.

## Privacy and local-first data

Tracked `data/*.example.json` files are fictional. Real profiles, policies, evidence, resumes, databases, artifacts, screenshots, and browser state are ignored. The runtime prefers `*.local.json` and falls back to examples for a safe first launch.

## ATS support status

| ATS | Discovery | Application automation |
|---|---:|---|
| Ashby | Supported | Real inspection/fill/control path validated; experimental |
| Greenhouse | Supported | Fixture-tested; experimental |
| Lever | Supported | Fixture-tested; experimental |
| Workday | Discovery support | Submission not validated |
| Generic/custom | Best effort | Per-site validation required |

Browser automation never bypasses CAPTCHA, authentication, access controls, or anti-bot protection. Authenticated LinkedIn automation is prohibited.

## Development

```bash
cd backend
python -m pytest -q
python -m compileall -q app tests

cd ../frontend
npm install
npm run lint
npm run build
```

## Roadmap

- Improve public contact intelligence using verified public sources
- Add outcome calibration without overstating small samples
- Validate more ATS application flows independently
- Expand opportunity-set and skill-demand insights

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Never include real candidate data or live application payloads in issues, fixtures, commits, or screenshots.

## License

Licensed under the [Apache License 2.0](LICENSE).
