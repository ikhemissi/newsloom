import json

import httpx2


def scripted_chat(
    request: httpx2.Request,
    *,
    unsupported: bool = False,
    snapshot: str = "test-deployment",
) -> httpx2.Response:
    payload = json.loads(request.content)
    keys = set(payload["response_format"]["json_schema"]["schema"]["properties"])
    if keys == {"truths"}:
        value: object = {"truths": ["The synthetic launch is Tuesday."]}
    elif keys == {"claims"}:
        value = {"claims": ["The synthetic launch is Monday." if unsupported else "Tuesday."]}
    elif keys == {"verdicts"}:
        value = {
            "verdicts": [
                {
                    "verdict": "no" if unsupported else "yes",
                    "reason": "The evidence says Tuesday." if unsupported else None,
                }
            ]
        }
    elif keys == {"reason"}:
        value = {"reason": "Unsupported synthetic claim." if unsupported else "Supported."}
    else:
        raise AssertionError("unexpected_metric_schema")
    return httpx2.Response(
        200,
        json={
            "id": "chat_test",
            "object": "chat.completion",
            "created": 1,
            "model": snapshot,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(value)},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )
