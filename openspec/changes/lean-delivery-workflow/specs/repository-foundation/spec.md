# Spec Delta

## MODIFIED Requirements

### Requirement: Honest ordered delivery
A change SHALL be complete only after local checks and CI pass and, when it changes
deployed behavior, its Azure deployment is verified. A check that cannot run SHALL
be recorded as a known gap, never reported as passed. The bootstrap SHALL NOT
provision future product resources or select the agent UI framework.

#### Scenario: Cloud checks have not run
- **WHEN** only local scaffold validation has succeeded
- **THEN** CI and Azure tasks remain unchecked and the bootstrap change stays active

#### Scenario: An acceptance check cannot run
- **WHEN** a remaining check needs conditions automation cannot provide, such as a
  signed-in regular-browser session
- **THEN** it is recorded in the known-gaps register with its change and reason
- **AND** the change may be archived without marking that check as passed

## ADDED Requirements

### Requirement: Lightweight delivery track
Tuning, prompt, bug-fix, documentation and operational changes that add no new
capability, resource, identity, permission, dependency or data contract SHALL NOT
require an OpenSpec change. They SHALL still pass local checks and CI, deploy
through azd when deployed behavior changes, and update the owning runbook.

#### Scenario: A prompt or ranking change is delivered
- **WHEN** a change only adjusts existing behavior within existing contracts
- **THEN** it ships as a commit with a descriptive message and a runbook update
- **AND** no proposal, spec, design or task artifacts are required

#### Scenario: A change adds a resource or permission
- **WHEN** a change introduces a cloud resource, identity, grant or data contract
- **THEN** it uses an OpenSpec change before implementation

### Requirement: Single check run per source
Deployment hooks SHALL reuse a passing full check for an identical source
fingerprint instead of rerunning it, and any source change SHALL invalidate that
result. CI SHALL always run the full suite.

#### Scenario: Several layers deploy the same commit
- **WHEN** the full check passed for the current source and another layer deploys
- **THEN** the hook reports the reused result and skips the suite
- **WHEN** any tracked or new source file changes
- **THEN** the next hook runs the full suite again
