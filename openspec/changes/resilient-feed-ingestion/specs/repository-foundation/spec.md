## MODIFIED Requirements

### Requirement: Validated initial feed catalogue
The repository SHALL retain 41 unique active feed sources and their category
allowlists after removing the broken Solo.io feed and retaining the existing
agentgateway feed. Offline validation MUST reject malformed shapes, unsupported
kinds, unknown fields, duplicate IDs/URLs, credential-bearing or non-HTTPS URLs,
and empty category filters without making network requests.

#### Scenario: Initial catalogue is checked
- **WHEN** the feed-validation command loads the committed catalogue
- **THEN** it reports 41 valid sources without contacting publishers

#### Scenario: Invalid configuration is supplied
- **WHEN** a catalogue violates its schema or contains duplicate identifiers
- **THEN** validation fails explicitly rather than silently omitting entries

#### Scenario: The broken publisher entry is retired
- **WHEN** the approved catalogue update is applied
- **THEN** `solo-io-blog` is absent and `agentgateway-blog` occurs exactly once
- **AND** the other source definitions and category allowlists remain unchanged
- **AND** historical source, queue and quarantine records are not deleted
