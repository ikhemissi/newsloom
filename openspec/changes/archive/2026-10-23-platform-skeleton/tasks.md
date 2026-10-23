# Tasks

## 1. Deployment inputs and permission preflight

- [x] 1.1 Record the selected `dev` subscription/France Central environment, proposed application group, PostgreSQL SKU/storage, model versions/SKUs/capacities, and an itemized cost estimate in ignored deployment inputs and safe change evidence; verify current service availability, capacity, quota, and model lifecycle before any resource write.
- [x] 1.2 Establish the approved workload access matrix and migration-administrator boundary; verify provisioning/RBAC/build permissions and supported Foundry role scopes from actual service metadata/documentation, stopping for a decision if one AIServices account cannot enforce the intended boundary.

## 2. Shared Azure resources and configuration

- [x] 2.1 Implement the dedicated application group, ACR, Consumption ACA environment, PostgreSQL 18 database/firewall/vector allowlist, and distinct managed identities; verify focused mocked-provider assertions for Newsloom's resource configuration, disabled password/admin authentication, scoped grants, and preservation guards.
- [x] 2.2 Add the key-disabled AIServices account and pinned enrichment, embedding, and decision deployments with variable capacities; verify focused configuration tests reject unsupported/incomplete model settings without introducing fallback models.
- [x] 2.3 Export the real application group and required resource/endpoint/identity outputs, wire relevant Terraform checks into the existing quality gate, and document names/inputs/outputs and preview commands; verify `bash scripts/check.sh` and all updated documentation links.

## 3. Versioned database initialization through azd

- [x] 3.1 Add a real migration runner/image and initial versioned migrations for pgvector, the migration ledger, and explicit workload principal mappings; verify repeat runs, serialization, rollback/error handling, and no domain tables or seeded news through focused migration tests, using disposable PostgreSQL 18/pgvector where applicable.
- [x] 3.2 Add the small remote-state-backed `migrations` azd layer and manual ACA job, with the separate migration identity as the Entra administrator; verify job configuration, managed-identity registry access, distinct state key, and dependency on actual application outputs.
- [x] 3.3 Implement the azd ACR-build and migration-execution hooks with immutable image references and bounded terminal-status checking; verify build/pull/SQL/execution failures propagate, document the phased preview/recovery commands, and confirm no placeholder image or direct provisioning command is used.

## 4. Telemetry and platform verification

- [x] 4.1 Configure workspace-based App Insights with local authentication disabled, ACA Azure Monitor diagnostic routing, and publishing grants; verify configuration tests demonstrate no workload-held workspace key and document the intended routing.
- [x] 4.2 Implement bounded synthetic database, model, identity allow/deny, and telemetry probes with safe result reporting; verify malformed model responses, non-1536/nonfinite embeddings, denied access, terminal failures, and content/credential canaries through focused tests of Newsloom's verification code.
- [x] 4.3 Add any temporary managed-identity verification jobs through azd, plus an explicit cleanup allowlist; document commands and expected output, and verify cleanup cannot target shared infrastructure or state resources.

## 5. Actual Azure deployment and acceptance

- [x] 5.1 Pass the local quality gate, review `azd provision application --preview` for the existing environment, and provision through azd; verify the full real resource inventory, separate application group, disabled local authentication, intended network settings, and unchanged bootstrap resource IDs.
- [x] 5.2 Build, preview, provision, and execute the migration layer through azd; verify successful terminal execution, PostgreSQL 18, installed pgvector, a 1536-dimensional vector operation, correct identity mappings, and repeatable migrations without domain tables.
- [x] 5.3 Run model-contract and access-boundary checks under the actual workload identities; verify approved operations succeed, prohibited operations fail, all configured model contracts pass, and the observed grant inventory matches the approved matrix without claiming later database DML behavior.
- [x] 5.4 Verify authenticated telemetry ingestion, rejection without Entra credentials, safe failure diagnostics, and absence of content/credential canaries; retain safe event/execution evidence and remove only temporary verification resources.
- [x] 5.5 Run `azd up` and repeat the relevant previews against the persistent environment; verify stable shared resource IDs and retained database state, record actual outcomes in this change, and keep ingestion/enrichment/MCP runtime delivery explicitly pending.

## 6. CI and implementation commit

- [x] 6.1 Commit the implementation only after local and Azure checks pass, push it, and verify GitHub Actions on that exact commit; record the commit/run and safe Azure evidence, keeping any failed or unverified acceptance task open.

## Workflow follow-up

- Archive this change only after all tracked acceptance gates pass; synchronize
  its implemented capability specs to the main specs and update canonical links.
- Continue with `feed-ingestion`; do not claim the platform foundation completes
  the runtime, MCP authentication, scanner calibration, or Phase 1 acceptance.

## Acceptance evidence

### Preflight - 2026-10-22

- Existing `dev` and France Central confirmed through azd; bootstrap names and
  tenant tag inputs preserved. Explicit platform settings were written with
  `azd env set`, not to tracked tenant-specific files.
- PostgreSQL capabilities advertise version 18 and `Standard_B1ms` without a
  restriction reason. Select 32 GiB/P4, seven-day backup retention, no HA, and no
  automatic storage growth. Physical capacity remains unproven until deployment.
- Select the design's exact model versions and SKUs with capacity 10 for GPT,
  10 for embeddings, and 60 for screening. Current quota used/limit is 100/1000,
  0/350, and 0/60 respectively. The model metadata reports inference retirement
  on 2027-09-21, 2028-02-09, and 2027-02-04 respectively. Capacity units follow
  each SKU's reported rate limits, not a universal TPM conversion.
- Retail API estimate in USD, excluding tax/discounts and existing state costs:
  PostgreSQL B1MS $0.019/hour (about $13.87/730 hours), 32 GiB disk at
  $0.133/GiB-month (about $4.26), ACR Basic $0.1666/day (about $5.07/month):
  about **$23.20/month before usage**. Registry builds are $0.0001/vCPU-second;
  logs are $2.76/GB before shared free allowances, with 30-day retention and a
  selected 0.1 GB/day development cap (not a hard spending limit). Consumption
  job execution, excess backup/registry storage, transfer, and model tokens are
  additional usage. GPT DataZone input/output is $0.825/$4.95 per million
  tokens; the Decision meter is $0.042 per million tokens. The selected Standard
  embedding regional meter is $0.000158/1K tokens ($0.158 per million), distinct
  from the Global and DataZone meters.
- The operator's live subscription permissions include `*` without exclusions,
  covering resource, role-definition/assignment, registry-build, and job actions.
- Live provider operations expose separate embedding, chat-completion, and
  AIServices-provider data actions. Custom roles use these account-scoped
  operations rather than the broad built-in OpenAI/User grants. Deployment-level
  model isolation is not claimed. Actual managed-identity allow/deny checks,
  including alternate inference routes, remain mandatory acceptance gates.
- Sources: [retail API](https://prices.azure.com/api/retail/prices),
  [OpenAI resource RBAC](https://learn.microsoft.com/azure/foundry-classic/openai/how-to/role-based-access-control),
  [keyless Foundry inference](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/configure-entra-id),
  and [Decision API](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision).
- Application Terraform validation and all three focused mocked-provider tests
  pass. The complete local gate also passes: 29 Python tests, three application
  tests, three existing bootstrap tests, strict typing, lint/format, identifiers,
  feed validation, and strict OpenSpec validation. Azure deployment is still
  pending; these results do not prove data-plane permissions or migrations.
- Full implementation gate on 2026-10-22: **75/75 Python tests**, including all
  four real PostgreSQL 18/pgvector integration tests, **9/9 mocked Terraform
  tests**, strict typing, format/lint, identifiers, catalogue, and OpenSpec checks
  passed. The disposable loopback-only Podman database was stopped and removed.
  The built package contains both versioned SQL resources. Documentation links,
  anchors, and Bash command syntax also pass.
- These were local implementation results, not Azure acceptance evidence.

### Azure deployment and acceptance - 2026-10-22

- Actual application resources were provisioned through `azd provision
  application` in `rg-newsloom-dev`, France Central: Basic ACR, Consumption ACA,
  PostgreSQL 18/B1ms/32 GiB, four distinct identities, key-disabled AIServices
  with all three configured model deployments, Log Analytics, and App Insights.
  Bootstrap resource-group/storage-account IDs match their retained state.
- PostgreSQL password authentication, registry admin access, model local keys,
  and LAW/App Insights local authentication are disabled. Only the documented
  Azure-services firewall rule is present; the vector extension is allowlisted.
  ACA uses Azure Monitor with no workspace key and its diagnostic setting points
  to the intended workspace. All explicitly provisioned taggable resources have
  the caller-supplied tenant tags.
- Initial provisioning exposed concurrent PostgreSQL child mutations
  (`ServerIsBusy`). Explicit dependencies now serialize those mutations. The
  provider's preservation guard also blocked an unintended ACA replacement:
  removing the unsupported non-VNet infrastructure-group name and preserving
  Azure's assigned PostgreSQL zone produced a **no-change** application preview.
  The later output-only deployment added/changed/destroyed **zero resources**.
- Real ACR builds succeeded. The migration layer now owns the real migration
  job and four temporary verification jobs, all using an immutable digest,
  managed-identity pull, and variable-derived tags. Build paths resolve the
  repository root; nested identity JSON uses a documented Base64 transport.
  The Foundry route was checked against the actual advertised service endpoint.
- Real migration execution `migrate-newsloom-dev-xc5ctay` succeeded. Replay
  `migrate-newsloom-dev-yyaw8c4` also succeeded, including validation of the
  existing Entra role mappings. Execution status and references are retained in
  ignored deployment evidence; older replica logs have already expired, so no
  unobserved migration-count claim is made.
- A real TLS/managed-identity database query under the enrichment identity
  reported server version **180006**, a successful **1536-dimensional** vector
  operation, and **zero public tables**. This independently verifies vector
  readiness without claiming domain schema or content-processing delivery.
- Initial enrichment verification failed with `database_denial_not_proven`.
  Bounded diagnostics confirmed that libpq omitted SQLSTATE for a server FATAL
  invalid-access-token-format rejection. The corrected conservative classifier
  was tested against that actual response before redeployment; network/TLS
  errors remain rejected as evidence.
- All four complete identity-probe executions succeeded for correlation
  `54ff2783aafe47e5b46b1443fdd25e70`: enrichment `8simmve`, ingestion `16czbjp`,
  MCP `q5tkhle`, and migrations `6s8klja` (their full names remain in ignored
  azd outputs). These prove the actual database/role denials, model allow/deny
  matrix and alternate-route/key-list denial, registry pull without push,
  authenticated telemetry submission, and rejected unauthorized submission.
  Sink arrival and content-free console aggregation subsequently passed.
- The Decision API's actual typed response uses `answers.ready.noul`, not a
  guessed `probability` property. Field/type-only diagnostics established this
  without logging response values; the deployed validator now checks that
  exact schema and finite 0-1 range.
- A read-only live grant audit matched the output inventory exactly: three
  scoped assignments for each runtime identity and one registry-pull assignment
  for migrations, with no extra assignments. Actual custom role data actions
  match the intended matrix; no deployment-level RBAC claim is made.
- The full `newsloom-platform verify` command completed successfully for that
  correlation. Actual AppEvents aggregation returned exactly one success event
  for each of enrichment, ingestion, and MCP. Actual console aggregation returned
  **four successful workloads and zero content/credential canary leaks**.
  Query results contain only safe outcome/count fields.
- Cleanup preserved the exact temporary-job allowlist in ignored evidence.
  Its reviewed preview contained **0 additions, 0 updates, 4 deletions**;
  azd applied exactly those four deletions. Read-back confirms that only the
  real migration job remains. No identity, shared service, bootstrap resource,
  or database was removed.
- Azure also generated an **untagged** `Failure Anomalies - appi-newsloom-dev`
  alert linked to an existing action group outside Newsloom. Neither that
  external group nor the generated alert's behavior has been modified. With
  explicit user approval, a one-time Azure CLI metadata update applied the
  two tag values from the existing ignored deployment inputs. Read-back verified
  the tags and identical alert properties. No new product tag requirement,
  permanent tagging mechanism, or tag-specific test has been introduced.
- Final complete local gate: **90/90 Python tests**, including four actual
  PostgreSQL 18/pgvector integration tests, **9/9 mocked Terraform tests**,
  strict typing, format/lint, identifiers, catalogue, and strict OpenSpec.
  The disposable local database was stopped and removed. The changed runbooks,
  README, and agent guidance also pass **55 local link/anchor checks** and
  **12 Bash-block syntax checks**.
- Full native `azd up --no-prompt` succeeded across bootstrap, application, and
  migrations. Bootstrap/application added, changed, and destroyed zero resources.
  The only migration-layer update was its immutable image after the README's
  status changed the build context; runtime code was unchanged from the accepted
  identity probes. The real migration replay
  `migrate-newsloom-dev-8pjgtfb` succeeded again.
- Subsequent previews of **all three layers report no changes**. A direct
  comparison with the saved remote-state baseline confirms **all 32 shared
  managed-resource IDs unchanged**. Final inventory contains only the retained
  migration job alongside shared services; all **12 inventory resources** retain
  both configured tenant tags, including the explicitly approved generated alert.
  Database/ledger state is retained and no ingestion, enrichment, or MCP business
  runtime is claimed.

### Exact-commit CI - 2026-10-22

- Implementation commit
  [`6176304cbb0aba00cc9a2d6feeef34de57328be3`](https://github.com/ikhemissi/newsloom/commit/6176304cbb0aba00cc9a2d6feeef34de57328be3)
  was committed and pushed only after local and Azure acceptance passed.
- [Local checks run 39855018985](https://github.com/ikhemissi/newsloom/actions/runs/39855018985)
  succeeded on that exact full SHA. Its actual logs confirm **90/90 Python
  tests**, including all four PostgreSQL 18/pgvector integration tests without
  skips, and **9/9 mocked Terraform tests** across all three roots. Lint/format,
  strict typing, identifiers, catalogue, Terraform validation, and strict
  OpenSpec checks also passed.
- All **17/17 tracked tasks** are complete. This evidence is persisted separately
  from the verified implementation commit. Business runtimes and PRD-1 phase
  acceptance remain pending.

### Archive - 2026-10-23

- Acceptance-evidence commit
  [`f80cf4f3967a2910366f163b46a0759c43f549bf`](https://github.com/ikhemissi/newsloom/commit/f80cf4f3967a2910366f163b46a0759c43f549bf)
  also passed [exact-commit CI](https://github.com/ikhemissi/newsloom/actions/runs/39855352142),
  including all 90 Python tests and nine mocked Terraform tests.
- With user approval, published all three delivered capabilities into main specs,
  verified that their Purpose, requirements, and scenarios match the accepted
  deltas, and passed strict validation of all four main specs before archiving.
- Archived this change with all artifacts and **17/17 tasks complete**. Updated
  canonical documentation links; no Azure resource or deployment state changed.
