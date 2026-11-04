# Spec Delta

## ADDED Requirements

### Requirement: Versioned production-input pins preserve frozen provenance
Evaluation tooling SHALL recognize only explicitly registered production-input
sets and report the digest of the actual matched bytes. A separately approved
UI-workspace manifest MUST NOT overwrite historical pins, relabel frozen
provenance, reset budgets or permit unknown source changes.

#### Scenario: The approved UI workspace exclusion changes the root manifest
- **WHEN** the manifest matches its separately pinned UI-workspace version and all other production inputs remain unchanged
- **THEN** offline verification returns that version's actual digest
- **AND** it does not return the historical manifest set's digest

#### Scenario: Historical inputs are verified
- **WHEN** the original pinned input set is supplied
- **THEN** its original digest remains unchanged
- **AND** existing serialized approval and receipt shapes are not rewritten

#### Scenario: An old approval is supplied for changed source
- **WHEN** frozen provenance identifies the historical input set but current source uses the UI-workspace set
- **THEN** current-source validation rejects that provenance before execution
- **AND** no halted run, counter or paid authorization is reactivated

#### Scenario: An unregistered production input changes
- **WHEN** any production input differs from both registered exact sets
- **THEN** verification fails explicitly
- **AND** it does not dynamically repin, substitute dependencies or waive the local gate
