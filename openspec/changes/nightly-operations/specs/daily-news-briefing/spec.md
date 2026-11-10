# Spec Delta

## Purpose

Start the daily briefing after the database wakes, keeping the 05:00 UTC slot.

## MODIFIED Requirements

### Requirement: Daily scheduled seven-day evidence window
The system SHALL run one shared briefing workflow daily for the 05:00 UTC slot,
starting at 07:45 UTC after the database wakes, using committed stored news
with publication instants in the half-open interval [scheduled cutoff minus
seven days, scheduled cutoff). The window MUST remain fixed despite delayed
execution, browser timezone, filters or article selection.

#### Scenario: A daily run starts late or a reader changes filters
- **WHEN** a scheduled run starts after 05:00 UTC
- **THEN** it retains that slot's 05:00 UTC cutoff, includes the lower boundary
  and excludes the upper boundary and future-dated records
- **AND** different readers, local timezones and browsing filters receive the
  same shared published version
