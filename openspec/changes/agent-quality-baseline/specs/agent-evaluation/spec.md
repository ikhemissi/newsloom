## MODIFIED Requirements

### Requirement: Private evaluation diagnostics and data handling
Evaluation diagnostics SHALL contain only allowlisted outcomes, case references,
counts, timings and fingerprints. Credentials, prompts, evidence, answers, judge
explanations and raw exceptions MUST NOT enter logs. Foundry artifacts MUST
contain only approved authored pilot data or content-free baseline metadata.
Baseline evidence/answers require separate approval for transient Azure judging.
Production-text persistence, vendor telemetry and external result sync are forbidden.

#### Scenario: Success, failure or forced instrumentation is exercised
- **WHEN** tests inject content and credential canaries through judging,
  publishing, errors and cancellation
- **THEN** diagnostics and unintended caches contain none of those canaries
- **AND** recorded outbound requests target only the approved Azure surfaces,
  with no vendor telemetry or external dashboard synchronization

#### Scenario: An evaluation artifact is retained
- **WHEN** the pilot uploads synthetic inputs, scores or bounded explanations
- **THEN** their data classification and observed retention/deletion behavior
  are recorded separately from content-free operational telemetry
- **AND** unavailable deletion proof is explicit and never claimed as successful
  cleanup; production text remains excluded from the pilot

#### Scenario: The operator explicitly approves real-agent baseline judging
- **WHEN** a separately approved baseline uses actual stored summaries and
  generated A2A answers
- **THEN** only bounded transient processing in the existing approved Azure
  model account is permitted, with credentials retained by their owning client
- **AND** saved results, IPC diagnostics and Foundry rows contain only opaque
  case/metric IDs, finite scores, hashes, fixed categories, timings and usage
- **AND** production-derived questions, preferences, summaries, answers and judge
  explanations enter no new baseline files, logs, caches, traces or remote artifacts
- **AND** existing A2A task/model-service retention is disclosed separately;
  transient processing does not imply physical-memory or provider-backup erasure

#### Scenario: A baseline artifact contains unexpected content
- **WHEN** a field contains raw content, an explanation, a token, a principal/
  deployment identifier or another unapproved value outside the strict schema
- **THEN** validation fails before persistence or publication without echoing
  the value or raw exception
- **AND** no hashed-field naming convention or baseline-mode flag permits raw
  content to bypass that validation
- **AND** the authored-only two-case pilot and its historical approvals remain
  unchanged, rather than inheriting the baseline's transient-data permission
