# Spec Delta

## Purpose

Make research a visible, refinable conversation on every screen size.

## ADDED Requirements

### Requirement: Conversation panel
The research panel SHALL show the conversation as a thread, keep the latest
question and answer in view while it streams, offer suggested follow-ups as
buttons, and allow starting a new conversation. It SHALL sit beside the content
on wide screens and as a full-height sheet on narrow screens. Threads are kept
in the browser tab only and cleared on sign-out.

#### Scenario: Follow-up question
- **WHEN** a reader asks a follow-up in an existing thread
- **THEN** the request carries the last turns of that thread, the new answer is
  scrolled into view and appended below the previous one

#### Scenario: Narrow screen
- **WHEN** the window is phone width
- **THEN** the panel opens as a full-height sheet with no horizontal scrolling
  and closing it returns focus to the control that opened it

#### Scenario: Sign-out
- **WHEN** the reader signs out
- **THEN** stored threads are removed from the browser
