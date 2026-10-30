import json

import httpx2
import pytest
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    CodeBasedEvaluatorDefinition,
    EvaluatorVersion,
)
from fakes import PROJECT_ENDPOINT, TOKEN, Credential
from openai import AuthenticationError


async def test_real_project_sdk_uses_entra_and_pages_precomputed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "foreign-key-must-not-be-used")
    requests: list[httpx2.Request] = []
    prefix = "/api/projects/pilot/openai/v1/evals"
    rows = [
        {"case_id": "supported", "score": 1.0, "reason": "Supported synthetic answer."},
        {"case_id": "unsupported", "score": 0.0, "reason": "Unsupported synthetic answer."},
    ]

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.url.host == "evaluation-test.services.ai.azure.com"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert "api-key" not in request.headers
        if request.method == "POST" and request.url.path == prefix:
            body = json.loads(request.content)
            criterion = body["testing_criteria"][0]
            assert criterion["type"] == "python"
            assert criterion["name"] == "imported_deepeval_faithfulness"
            assert (
                criterion["source"] == "def grade(sample, item):\n    return float(item['score'])\n"
            )
            assert criterion["pass_threshold"] == 0.5
            assert set(criterion) == {"type", "name", "source", "pass_threshold"}
            return httpx2.Response(
                200,
                json={
                    "id": "eval_test",
                    "object": "eval",
                    "created_at": 1,
                    "name": "synthetic-import",
                    "metadata": {"source": "synthetic"},
                    "data_source_config": body["data_source_config"],
                    "testing_criteria": body["testing_criteria"],
                },
            )
        if request.method == "POST" and request.url.path == prefix + "/eval_test/runs":
            body = json.loads(request.content)
            assert body["data_source"] == {
                "type": "jsonl",
                "source": {"type": "file_content", "content": [{"item": row} for row in rows]},
            }
            return httpx2.Response(
                200,
                json={
                    "id": "run_test",
                    "object": "eval.run",
                    "eval_id": "eval_test",
                    "created_at": 1,
                    "status": "completed",
                    "report_url": "https://ai.azure.com/synthetic-report",
                    "data_source": body["data_source"],
                    "metadata": {},
                },
            )
        assert request.method == "GET"
        assert request.url.path == prefix + "/eval_test/runs/run_test/output_items"
        index = 1 if request.url.params.get("after") == "item_one" else 0
        identifier = "item_two" if index else "item_one"
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": identifier,
                        "object": "eval.run.output_item",
                        "created_at": 1,
                        "eval_id": "eval_test",
                        "run_id": "run_test",
                        "datasource_item_id": index,
                        "datasource_item": rows[index],
                        "status": "completed",
                        "results": [
                            {
                                "name": "imported_deepeval_faithfulness",
                                "type": "python",
                                "status": "completed",
                                "score": rows[index]["score"],
                                "passed": index == 0,
                            }
                        ],
                        "sample": {},
                    }
                ],
                "first_id": identifier,
                "last_id": identifier,
                "has_more": index == 0,
            },
        )

    async with (
        Credential() as credential,
        AIProjectClient(
            endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True, retry_total=0
        ) as project,
        project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(respond), trust_env=False, follow_redirects=False
            ),
        ) as client,
    ):
        definition = await client.evals.create(
            name="synthetic-import",
            data_source_config={
                "type": "custom",
                "item_schema": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string"},
                        "score": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["case_id", "score", "reason"],
                },
            },
            testing_criteria=[
                {
                    "type": "python",
                    "name": "imported_deepeval_faithfulness",
                    "source": "def grade(sample, item):\n    return float(item['score'])\n",
                    "pass_threshold": 0.5,
                }
            ],
            metadata={"source": "synthetic"},
        )
        run = await client.evals.runs.create(
            definition.id,
            data_source={
                "type": "jsonl",
                "source": {
                    "type": "file_content",
                    "content": [{"item": row} for row in rows],
                },
            },
        )
        outputs = [
            row
            async for row in client.evals.runs.output_items.list(
                run.id, eval_id=definition.id, limit=1
            )
        ]
    assert credential.closed
    assert credential.scopes == [("https://ai.azure.com/.default",)]
    assert len(requests) == 4
    assert [row.datasource_item for row in outputs] == rows
    assert [row.results[0].score for row in outputs] == [1.0, 0.0]
    assert run.report_url == "https://ai.azure.com/synthetic-report"


async def test_real_projects_openai_bridge_does_not_retry_authentication_failure() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(401, json={"error": {"message": "synthetic denied"}})

    async with (
        Credential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
        ) as client,
    ):
        with pytest.raises(AuthenticationError):
            await client.evals.retrieve("eval_test")
    assert len(requests) == 1


def test_historical_projects_code_evaluator_serialization() -> None:
    code = "def grade(sample, item):\n    return float(item['score'])\n"
    definition = EvaluatorVersion(
        evaluator_type="custom",
        categories=["quality"],
        display_name="imported_deepeval_faithfulness",
        supported_evaluation_levels=["turn"],
        metadata={"origin": "deepeval"},
        definition=CodeBasedEvaluatorDefinition(code_text=code),
    )
    serialized = definition.as_dict()
    assert serialized["definition"]["type"] == "code"
    assert serialized["definition"]["code_text"] == code
    assert serialized["metadata"] == {"origin": "deepeval"}
