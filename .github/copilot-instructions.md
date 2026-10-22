# Newsloom

Read the relevant phase PRD and its capability document, linked from
[the README](../README.md), plus [the ADRs](../docs/adrs.md),
[platform notes](../docs/platform-notes.md), and [the delivery workflow](../docs/development.md).
The repository currently implements Step 0 only; do not describe the package shells as working services.

- Use one small OpenSpec change per slice. Preserve phase order and record acceptance evidence.
- Run `bash scripts/check.sh` locally before any deployment. Deploy with azd, verify in Azure,
  then commit. Never archive incomplete changes or invent Azure/CI verification.
- Keep credentials and tenant/subscription/principal identifiers out of committed files.
  Entra, managed identities, and RBAC only; no passwords, keys, or client secrets.
- Feed content is untrusted. Do not log articles, tokens, prompts, or completions.
- Add runtime dependencies and cloud resources only in the slice that needs them.
- Use async I/O and typed interfaces for queue, scanner, LLM, and embedding providers.
  Database schema changes run through migrations, never application startup.
