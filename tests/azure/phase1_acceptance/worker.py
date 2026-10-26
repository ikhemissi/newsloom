import asyncio
import json
import time

import httpx
from azure.core.credentials_async import AsyncTokenCredential
from newsloom_core.model_transport import ModelClient
from newsloom_core.phase1_contracts import AcceptanceFailure, TestConfig
from newsloom_enrichment.job import run
from newsloom_enrichment.models import Claim, Enrichment, Vector
from newsloom_enrichment.providers import FoundryEmbedding, FoundryLlm, revisions
from newsloom_enrichment.repository import ModelMetadata, Repository
from newsloom_platform import phase1_database


class ObservedRepository:
    def __init__(self, current: Repository, pause: bool) -> None:
        self.current, self.pause = current, pause

    async def claim(self, correlation: str) -> Claim | None:
        claim = await self.current.claim(correlation)
        if claim is not None:
            print(
                json.dumps(
                    {
                        "event": "phase1_claim",
                        "id": claim.id.hex,
                        "attempt": claim.attempts,
                    }
                ),
                flush=True,
            )
            if self.pause:
                await asyncio.Future[None]()
        return claim

    async def complete(
        self,
        claim: Claim,
        result: Enrichment,
        vector: Vector,
        metadata: ModelMetadata,
        correlation: str,
    ) -> None:
        await self.current.complete(claim, result, vector, metadata, correlation)

    async def fail(
        self,
        claim: Claim,
        category: str,
        retry_after: float,
        correlation: str,
    ) -> None:
        await self.current.fail(claim, category, retry_after, correlation)

    async def counts(self) -> dict[str, int]:
        return await self.current.counts()


async def work(config: TestConfig, credential: AsyncTokenCredential, *, pause: bool) -> None:
    started = time.monotonic()
    async with (
        httpx.AsyncClient() as client,
        await phase1_database.connect(config, credential) as connection,
    ):
        model = ModelClient(client, credential, config.model_endpoint)
        prompt, taxonomy = revisions()
        metadata = ModelMetadata(
            config.generation_model,
            config.generation_version,
            config.embedding_model,
            config.embedding_version,
            prompt,
            taxonomy,
        )
        counts = await run(
            ObservedRepository(Repository(connection), pause),
            FoundryLlm(model, config.generation_deployment),
            FoundryEmbedding(model, config.embedding_deployment),
            metadata,
            config.run_id,
            limit=1,
        )
        if counts["enriched_run"] != 1 or counts["failed_run"] or counts["lease_lost_run"]:
            raise AcceptanceFailure("acceptance_worker_failed")
        usage = model.observations
        print(
            json.dumps(
                {
                    "event": "phase1_worker",
                    "completed": 1,
                    "generation_calls": usage.generation_calls,
                    "embedding_calls": usage.embedding_calls,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            ),
            flush=True,
        )
