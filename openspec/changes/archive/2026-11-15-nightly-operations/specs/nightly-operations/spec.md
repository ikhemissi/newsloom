# Spec Delta

## Purpose

Keep a restorable copy of the data outside the database server and run the
server only during the day.

## ADDED Requirements

### Requirement: Daily database export
The system SHALL export the application database once a day to a dedicated
storage account as a `pg_dump` custom-format archive with a manifest of its
byte size, SHA-256 and row count per table. Exports MUST NOT be overwritten or
deleted for 30 days and MUST be retained for about 60 days. Access MUST use
managed identities and Entra only; the exporting identity MUST have read-only
database access. Logs MUST NOT contain stored content.

#### Scenario: The nightly export succeeds
- **WHEN** the nightly job runs
- **THEN** a dump and its manifest are written under the day's path
- **AND** the manifest's size and SHA-256 match the uploaded dump

#### Scenario: The export fails
- **WHEN** the dump or upload fails
- **THEN** no manifest is written, the job reports failure and the server is
  still stopped

#### Scenario: An operator verifies a backup
- **WHEN** the restore drill restores the latest dump into a local PostgreSQL
- **THEN** every table's row count equals the manifest

### Requirement: Daily operating window
The server SHALL be stopped after the nightly export at 23:00 UTC and started
at 07:00 UTC. Ingestion and enrichment SHALL run only between 07:10 and
22:40 UTC. After starting the server, the wake job SHALL merge the
`CostControl` and `SecurityControl` governance tags onto the resource group and
the resources in it that lack them, without removing or changing other tags.

#### Scenario: Governance removed the tags overnight
- **WHEN** the wake job runs and some resources lack the governance tags
- **THEN** it starts the server and adds the two tags to those resources

#### Scenario: Governance blocked the Terraform state storage
- **WHEN** the state resource group lost its tags or the state account's public
  network access was disabled
- **THEN** the wake job merges the tags back and re-enables public network access,
  using grants limited to that resource group and account

#### Scenario: The server is already in the target state
- **WHEN** the server is already stopped at night or running in the morning
- **THEN** the job succeeds without changing it

### Requirement: Protection against deletion
The PostgreSQL server and the backup storage account SHALL carry delete locks,
and built-in point-in-time backups SHALL be retained for 35 days.

#### Scenario: Something tries to delete the server
- **WHEN** a delete request reaches the locked server or storage account
- **THEN** Azure refuses it until an operator removes the lock
