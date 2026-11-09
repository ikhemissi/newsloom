"""Shared workload services; neither protocol surface owns separate capacity."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from newsloom_core.briefing import BriefingRead

from newsloom_mcp.embedding import QueryEmbedding
from newsloom_mcp.feedback import FeedbackStore
from newsloom_mcp.radar import RadarStore
from newsloom_mcp.repository import NewsRepository


@dataclass(frozen=True)
class Services:
    repositories: Callable[[], AbstractAsyncContextManager[NewsRepository]]
    embeddings: QueryEmbedding
    ready: Callable[[], Awaitable[bool]]
    observe: Callable[[str, str, float], None] | None = None
    observe_http: Callable[[str, str, float], None] | None = None
    observe_api: Callable[[str, str, str, float], None] | None = None
    model_revision: str = ""
    briefing: Callable[[datetime], Awaitable[BriefingRead]] | None = None
    feedback: Callable[[], AbstractAsyncContextManager[FeedbackStore]] | None = None
    feedback_reviewers: frozenset[UUID] = frozenset()
    radar: Callable[[], AbstractAsyncContextManager[RadarStore]] | None = None
