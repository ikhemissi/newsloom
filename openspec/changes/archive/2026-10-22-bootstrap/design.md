# Design

## Context

The repository starts empty apart from a temporary specification. Step 0 must
enable small subsequent changes without prematurely implementing later phases.
Infrastructure uses Terraform through azd with RBAC-only remote state; developer
and CI checks must not need Azure credentials or a database.

## Goals / Non-Goals

**Goals:** preserve requirements and operational context in standalone PRDs,
capability documents, ADRs, and platform notes without a duplicate full specification;
provide a locked Python workspace and OpenSpec workflow, validate the initial feed
configuration, and prepare safe state-bootstrap configuration.

**Non-Goals:** production services, database/network/model infrastructure, automatic
cloud deployment, a UI framework choice, or assumptions about subscription/region.

## Decisions

1. Use stable Python 3.15.1, one uv workspace and src-layout packages. Service shells
   are importable distributions, not misleading successful CLI jobs or open APIs.
   Alternative: implementing service placeholders would blur acceptance boundaries.
2. Keep only shared configuration code and its Pydantic dependency at bootstrap.
   Install cloud SDKs, migration tools, MCP/Agent Framework and telemetry in the
   slices that need them to avoid speculative dependency coupling.
3. Use strict mypy, Ruff and pytest, a single local/CI check script, and lightweight
   pre-commit hooks. Validate Terraform without initializing the Azure backend.
4. Keep state infrastructure in an independent Terraform root, provisioned through
   azd's native `bootstrap` layer. Its local state lives under the existing azd
   environment at `.azure/<environment>/infra/bootstrap/terraform.tfstate`, avoiding
   a backend creating itself. The `application` layer depends on bootstrap, consumes
   its `RS_*` outputs for the RBAC backend, and contains no app resources yet.
   Both layers accept caller-supplied common tags through Terraform variable
   maps. Shared keys and anonymous blobs are disabled; retain
   versioned state and prevent accidental destruction. Adopt any existing local
   bootstrap state without recreating resources. Do not provision through direct
   Terraform CLI commands.
5. Generate GitHub Copilot OpenSpec integration with the pinned CLI. Keep this change
   active until CI and real Azure data-plane/lease checks are verified.

## Risks / Trade-offs

- Initial state provisioning requires resource-creation and role-assignment rights;
  RBAC propagation can delay data-plane verification. Never bypass with keys.
- Bootstrap state must be preserved securely outside Git. Main environment state
  is remote; neither environment should be recreated casually.
- Publisher endpoints/terms and security behavior are not proven by configuration
  validation. Those checks belong to feed-ingestion and content-security.
- Latest stable Python needs current uv and compatible wheels. Lock dependencies
  and verify builds/type checks before accepting upgrades.
- CI requires pushing tested work and cloud acceptance requires explicit environment
  selection; neither is falsely marked complete by local scaffolding.
