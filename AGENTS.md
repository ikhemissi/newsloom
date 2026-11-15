# Agent instructions

## Context and sources

- Newsloom is deployed in one development environment: ingestion, enrichment,
  briefing, MCP and news API, the A2A research agent (conversations, web research)
  and the web app, with nightly operations. The [README](README.md) summarises
  what runs; each capability's runbook in `docs/` owns its operations and status,
  and [known gaps](docs/known-gaps.md) lists checks that could not run.
- Follow [documentation ownership](docs/development.md#documentation-ownership).
  Read the relevant phase PRD and capability document before changing behavior;
  use [ADRs](docs/adrs.md) for decisions and [platform notes](docs/platform-notes.md)
  for operational lessons. Link to requirements instead of maintaining copies.
- OpenSpec's delivered repository contract is in the
  [main spec](openspec/specs/repository-foundation/spec.md).
  Active changes describe planned additions; archives retain acceptance evidence.

## Working rules

- Pick the [delivery track](docs/development.md#choose-a-delivery-track): OpenSpec
  only for new capabilities, resources, identities, permissions, dependencies or
  data contracts; otherwise commit with a runbook update. Never invent verification
  evidence; record checks that cannot run in [known gaps](docs/known-gaps.md).
- Preview model-driven changes locally (record/replay) before deploying them.
- Run local checks before deployment. Use the existing azd environment and preserve
  its state; never casually recreate infrastructure. See the
  [state runbook](docs/azure-bootstrap.md) for setup and recovery.
- Keep credentials and tenant/subscription/principal identifiers out of committed
  files. Use Entra, managed identities, and RBAC; no passwords, keys, or client secrets.
- Feed content is untrusted data. Never log article text, tokens, credentials,
  prompts, or completions.
- Add dependencies and cloud resources only in their owning slice. Use async I/O
  and typed queue, scanner, LLM, and embedding interfaces. Apply schema changes
  through migrations, never application startup.

## Validation

Install dependencies using the [README](README.md#build-and-test). The primary
check is `bash scripts/check.sh`; it is also used by CI and azd hooks.

| Change | Focused command |
| --- | --- |
| Python behavior | `uv run pytest` |
| Types | `uv run mypy` |
| Package builds | `uv build --all-packages` |
| OpenSpec artifacts | `npm run spec:check` |

For documentation-only changes, check local links/anchors and command syntax.
Keep human setup and deployment guidance in the README or runbooks, not here.
