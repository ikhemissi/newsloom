# content-screening Specification

## Purpose

Admit feed entries through real prompt-injection screening and retain rejected
or deferred content without allowing it into the accepted processing path.

## Requirements

### Requirement: Real model-based admission
Every eligible new entry SHALL pass the typed scanner boundary and configured
Microsoft-Decision-1 deployment before acceptance. The scanner MUST inspect
normalized content as untrusted data and validate the decision response.
The deployed job MUST NOT provide a no-op scanner, bypass flag, or acceptance
fallback when configuration, authentication, or response validation fails.

#### Scenario: A valid screening decision is received
- **WHEN** the configured Decision API returns its typed `noul` answer
- **THEN** the scanner requires a finite probability in the inclusive range 0 to 1
  and derives the verdict from the recorded threshold
- **AND** it does not generate a news summary, category, or embedding

#### Scenario: Screening cannot establish a decision
- **WHEN** the model response is malformed, unauthorized, unavailable, or times out
- **THEN** the entry remains unaccepted with an explicit safe failure category
- **AND** no alternative model or accept-everything implementation is substituted

### Requirement: Calibrated explicit threshold
The screening threshold SHALL be derived from labelled calibration examples and
verified against separate clean/hostile validation fixtures before live admission.
Threshold, model configuration, class counts, and observed classification outcomes
MUST be recorded. A threshold MUST NOT be guessed merely to enable deployment.

#### Scenario: Screening is enabled for live entries
- **WHEN** the proposed threshold is evaluated on the validation fixtures
- **THEN** expected clean fixtures are accepted and hostile fixtures are rejected,
  with the observed results retained as evidence
- **AND** unmet fixture expectations block live admission rather than weaken the gate

### Requirement: Distinct accepted rejected and deferred outcomes
Accepted entries SHALL enter `ingestion_queue` as pending. Rejected entries SHALL
be retained in `quarantine` with normalized content and bounded decision metadata.
Failures and budget deferrals MUST remain distinguishable from model rejections,
persist for retry, and never become pending accepted work.

#### Scenario: A model rejects an entry
- **WHEN** its probability exceeds the calibrated threshold
- **THEN** its normalized entry, decision score/reason, and timestamp are stored
  in quarantine instead of accepted work
- **AND** it is neither enriched nor automatically deleted

#### Scenario: A deferred entry is retried successfully
- **WHEN** a later bounded attempt establishes a valid acceptance decision
- **THEN** its transition to the pending queue is atomic and duplicate-free
- **AND** a prior permanent rejection is not automatically retried as an error

### Requirement: Bounded scanner throughput
Model calls SHALL respect the existing deployment's configured rate limit and the
job deadline, including retries and calibration calls. Excess or failed work MUST
be retained for bounded retry rather than dropped or accepted to finish the run.

#### Scenario: Capacity or time is exhausted
- **WHEN** the scanner reaches its rate budget, receives throttling, or lacks time
  to finish remaining entries
- **THEN** backoff respects the remaining deadline and outstanding work is explicitly
  deferred without losing its normalized content

### Requirement: Observable private screening
Scanner diagnostics SHALL expose only correlated outcome counts, timings, and safe
error categories. Entry text, questions, response bodies, credentials, and rejection
content MUST remain absent from telemetry. Quarantine MUST NOT be exposed through
the later news-serving path.

#### Scenario: Clean hostile and error paths are exercised
- **WHEN** labelled fixtures and actual managed-identity calls exercise the scanner
- **THEN** queue/quarantine aggregates agree with their observed dispositions and
  failure paths remain visibly unaccepted
- **AND** captured output excludes content and credential canaries
