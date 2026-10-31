## MODIFIED Requirements

### Requirement: Evidence-bounded synthesis and absence
Research answers SHALL use only validated MCP evidence from the current request.
The agent MUST distinguish a supported comparison, limited evidence and no match.
Stored summary/metadata detail MUST NOT be represented as full-article access.
Tool or model failure MUST NOT become a successful model-recollection answer.
Synthesis schemas MUST bind coverage and missing IDs from trusted application
state; independent validation MUST reject mismatches without repair.

#### Scenario: Multiple items support an answer
- **WHEN** stored summaries contain evidence relevant to the question
- **THEN** the response distinguishes supported agreements, differences and limits
- **AND** similarity scores are not described as factual confidence or probability

#### Scenario: Evidence is empty, insufficient or unavailable
- **WHEN** tools return no matching evidence, evidence lacks the requested detail,
  or a required tool operation fails
- **THEN** absence/insufficiency is explicit, and operational failure remains failure
- **AND** neither missing evidence nor a failed read is repaired by invented news

#### Scenario: Discovery supplies final evidence
- **WHEN** a discovery request reaches synthesis with validated detail evidence
- **THEN** the model's final schema permits only discovery coverage and the
  application's actual missing-item set
- **AND** the resulting validated answer preserves that coverage without a
  follow-up repair call or application rewriting model output

#### Scenario: Selected-item coverage is incomplete
- **WHEN** the application's selected-item retrieval finds missing records
- **THEN** its final schema binds the actual complete, partial or none coverage
  and missing IDs rather than asking the model to infer that metadata
- **AND** duplicate, foreign or inconsistent returned missing IDs still fail
  independent validation before answer text is emitted

#### Scenario: Untrusted content asks for different coverage
- **WHEN** a question or retrieved field asks the model to change coverage or
  remove missing IDs
- **THEN** that text cannot change the application's synthesis scope or schema
- **AND** a provider response contradicting the scope fails explicitly without
  changing evidence, budgets, caller authority or the answer to obtain a pass
