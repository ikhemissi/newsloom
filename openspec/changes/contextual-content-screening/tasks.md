# Tasks

Only checked tasks below are verified. Follow the acceptance gates in
[the delta](specs/content-screening/spec.md) and implementation decisions in
[the design](design.md). Groups 1-3 may be developed without production changes;
group 5 is blocked until all group 4 checks and measured evaluation pass.

## 1. Contextual question and production-shaped calibration

- [x] 1.1 Add the fixed contextual question, evaluation-only baseline, and authored complete-entry fixtures with at least eight benign/eight hostile cases in each of the calibration and separate validation splits. Verify typed fixture loading, distinct case IDs/splits, metadata coverage, quoted-versus-operative instruction pairs, long inputs, and legacy hostile regressions in focused scanner tests.
- [x] 1.2 Reuse production serialization and the existing request/response adapter for calibration and comparison. Verify that only calibration scores choose the midpoint, overlap and validation errors fail explicitly, and strict numeric admission, deadlines, retry bounds, invalid-response handling, and operational deferral remain unchanged.
- [x] 1.3 Update the screening explanation in the ingestion runbook, P1-C03 capability document, and ADR-6 without duplicating requirements. Verify links and that the documents distinguish contextual classification from sanitization or a guarantee of safety.

## 2. Policy-bound runtime configuration

- [x] 2.1 Implement the compact calibration identifier and wire it with the threshold through the existing ingestion CLI, azd parameters, and Terraform environment. Verify missing/malformed/mismatched bindings fail before admission, evaluation/calibration need no admission binding, and focused CLI/scanner and infrastructure tests cover question, fixture, model, endpoint/deployment, and threshold changes.
- [x] 2.2 Document calibration output, matching configuration, in-place rollout, and image-plus-calibration rollback in the ingestion runbook. Verify the documented commands against CLI help and retain the existing schedule, managed identity, state, and resource boundaries.

## 3. Side-effect-free local comparison

- [x] 3.1 Add the early-dispatched local comparison command using existing signed-in Entra credentials, the shared scanner transport, and a bounded sequential request budget. Verify explicit authorization/inference failures, retry accounting, and tests proving no database connection, managed-identity fallback, job start/update, azd write, or publishing occurs.
- [x] 3.2 Load private labelled review inputs or reconstruct only the selected identities from their three feeds using existing protected retrieval/parsing/recovery. Verify identity matching, complete serialization, provenance/fingerprints/truncation, blocking missing or ambiguous matches, safe cache cleanup on success/failure, and no article redirects; keep the normal one-RSS/one-Atom smoke restriction tested and unchanged.
- [x] 3.3 Emit content-free per-case and aggregate baseline/candidate results with explicit failed gates and no success-shaped inference failures. Verify report schema, fixed labels, independent threshold selection, complete denominators, and privacy canaries on success/error/logging paths; document local preflight, bounded comparison, private-input handling, and report interpretation in the ingestion runbook.
- [x] 3.4 Add the explicitly requested existing-job comparison command using only its managed identity and the shared evaluation pipeline, with bounded identity-only arguments and safe per-case/summary records. Verify no database or admission/configuration mutation, no raw article inputs in arguments/logs, deterministic same-input comparison, and document the native immutable execution override and activation sequence.

## 4. Local acceptance and measured evidence

- [x] 4.1 Run the focused scanner/CLI/repository/telemetry and configuration tests, then `bash scripts/check.sh` and `uv build --all-packages`. Retain actual results and resolve regressions before any deployment; do not add dependencies or relax checks to obtain a pass.
- [x] 4.2 Retain the frozen 23-item manifest and separate validation labels; use the explicitly requested existing-job managed-identity preflight after recording the failed local preflight and verified removal of its temporary grant. Verify all identities, provenance, normalization limits, and baseline threshold/configuration without database access, keys, new grants, separate workers, or production admission writes.
- [x] 4.3 Run the bounded baseline/candidate comparison locally or in the explicitly requested existing-job execution and retain a safe measured report and an article-by-article comparison in docs/findings/ with public identities, before/after verdicts, scores/thresholds, human-assessed motives, and potential false-positive counts distinguished from model explanations. Verify separable candidate calibration, zero benign/hostile holdout errors, strictly fewer benign rejections on the fixed 23-item set, complete inference, and no silent omissions. A failed gate blocks group 5; changed rubrics require a fresh holdout rather than relabelling inspected cases.

## 5. Existing-environment Azure delivery and acceptance

- [x] 5.1 After local acceptance, preserve rollback values, set only the measured threshold/binding in the existing ignored azd environment, and review the native preview before deployment. Verify only expected in-place image/configuration updates, with no resource replacement, schedule/identity/permission changes, or state recreation.
- [x] 5.2 Deploy through the existing azd flow and invoke ordinary ingestion immediately, without waiting for the schedule. Verify operator readback and safe telemetry for dispositions/counters, deduplication on replay, and operational failure behavior; retain local database-test evidence that existing rejected rows cannot be reconsidered and distinguish it from aggregate Azure evidence. Roll back the matched image/calibration if verification fails.
- [x] 5.3 After local and Azure verification, commit and push the implementation with the required trailer and verify CI for that exact commit. Record the commit and actual workflow outcome, not a previous run or an uncommitted local result.
- [x] 5.4 Update owning runbook/phase status and this change's acceptance evidence with measured local/Azure/CI results, limitations, and unchanged quarantine behavior. Verify documentation links, safe committed content, and exact-commit CI for any separate evidence commit; leave any unverified task unchecked.

## Acceptance evidence

- Contextual question, typed full-entry calibration/validation and legacy
  regression fixtures, shared baseline/candidate transport/rate budget, runtime
  calibration binding, explicit local/existing-job comparison and safe reports
  are implemented and activated.
- The complete final local gate passed 226 Python tests (one opt-in live
  publisher test skipped), 15 Terraform tests, typing/lint/format and other
  primary checks; all five workspace packages built. The focused scanner/CLI/
  evaluation/privacy suite passed 57 tests.
- Local database tests used a disposable PostgreSQL 18/pgvector container bound
  to loopback. It was stopped after testing. No cloud database access was used.
- The 23 private labels were frozen before inference. Developer preflight
  returned `401 PermissionDenied`. The user separately approved a temporary
  assignment of the existing inference-only role; bounded preflight still did
  not pass. That exact assignment was independently verified removed.
- The user then explicitly requested testing in the existing feed job.
  Execution `ingest-newsloom-dev-bzbi8b4` used a native immutable-image override
  and the unchanged ingestion managed identity, with no new grant/worker.
  It completed 126 paired observations in 131.76 seconds. Current-feed input
  fingerprints matched across policies for all 23 review identities.
- The measured threshold is `0.5478523630419381`, selected only from 16
  calibration cases. The 16 separate holdouts had zero candidate errors; all
  eight legacy attacks were rejected. Review rejections fell from 22 to 2,
  with no operational errors or dropped inputs. All gates passed.
- [Findings](../../../docs/findings/contextual-content-screening.md) preserve
  all 23 public identities, historical rejections, reviewer-assessed possible
  triggers, per-article measured scores/verdicts, remaining potential false
  positives, and local access limitations without article content or invented
  model explanations.
- After gates passed, azd preview/apply updated only the existing ingestion job:
  0 added, 1 in-place change, 0 destroyed. Direct readback verified unchanged
  resource ID, identity, schedule/configuration and ordinary run arguments,
  with the evaluated image/threshold/binding.
- Immediate `ingest-newsloom-dev-jd1tel7` and forced
  `ingest-newsloom-dev-bc7abmm` executions succeeded. Both reported 40 successful
  feeds and the existing OpenAI `entry_limit` failure, not a scanner failure.
  No new eligible items were staged; forced replay found 2,165 occurrences,
  including 1,893 known and 272 filtered.
- Independent readbacks after both runs showed 1,969 screened pending,
  23 rejected, 0 deferred, 0 duplicate URLs/GUIDs. Existing rejected rows were
  not released; aggregate counts do not establish historical per-row byte
  equality. Authenticated metrics and traces were observed for both runs.
- Implementation `cafff0adb41e729b973fbf7d5882e85efeb50027` was committed and
  pushed after local/Azure verification. Its
  [exact-commit CI](https://github.com/ikhemissi/newsloom/actions/runs/39997178176)
  completed successfully.
- azd's native initialization refreshed its local ingestion provider to AzureRM
  5.11 under the existing constraint. The incidental upgrade was not retained:
  the original 5.10 lock was restored and read-only initialization, validation,
  and all six ingestion Terraform tests passed again. No provider constraint
  or dependency change is included.
- No archival has been performed.
