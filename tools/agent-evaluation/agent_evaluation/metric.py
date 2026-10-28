import math
from typing import Protocol, Self

from deepeval.metrics import FaithfulnessMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from pydantic import BaseModel

from agent_evaluation.policy import EvaluationFailure, verify_privacy


class StructuredCompletion(Protocol):
    async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...


class Judge(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
    def __init__(self, completion: StructuredCompletion) -> None:
        verify_privacy()
        self.completion = completion
        super().__init__(model="newsloom-fixed-azure-judge")

    def load_model(self, *args: object, **kwargs: object) -> Self:
        return self

    def generate(self, *args: object, **kwargs: object) -> str:
        raise EvaluationFailure("synchronous_judge_forbidden")

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None) -> str:
        verify_privacy()
        if schema is None:
            raise EvaluationFailure("judge_schema_required")
        result = await self.completion.complete(prompt, schema)
        if not isinstance(result, schema):
            raise EvaluationFailure("judge_schema_mismatch")
        return result.model_dump_json()

    def get_model_name(self, *args: object, **kwargs: object) -> str:
        return "newsloom-fixed-azure-judge"


async def measure(
    completion: StructuredCompletion, *, question: str, evidence: str, answer: str
) -> tuple[float, str]:
    verify_privacy()
    metric = FaithfulnessMetric(
        model=Judge(completion),
        eval_mode="llm",
        async_mode=True,
        include_reason=True,
        verbose_mode=False,
    )
    score = await metric.a_measure(
        LLMTestCase(input=question, actual_output=answer, retrieval_context=[evidence]),
        _show_indicator=False,
    )
    reason = metric.reason
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
        or not isinstance(reason, str)
        or not reason.strip()
        or not 1 <= len(reason.encode()) <= 4096
        or metric.error is not None
    ):
        raise EvaluationFailure("invalid_faithfulness_result")
    return float(score), reason
