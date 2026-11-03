"""Read-only briefing projection; generation is never part of API access."""

from datetime import UTC, datetime, timedelta

from newsloom_core.briefing import Briefing, BriefingRead
from psycopg import AsyncConnection


async def read_briefing(
    connection: AsyncConnection[tuple[object, ...]], cutoff: datetime
) -> BriefingRead:
    current = await connection.execute(
        "SELECT payload FROM public.briefing_current WHERE singleton"
    )
    row = await current.fetchone()
    artifact = Briefing.model_validate(row[0]) if row else None
    status = await connection.execute(
        "SELECT status,started_at FROM public.briefing_status WHERE cutoff=%s", (cutoff,)
    )
    run = await status.fetchone()
    state = str(run[0]) if run else "pending"
    if (
        state == "running"
        and run is not None
        and isinstance(run[1], datetime)
        and run[1] <= datetime.now(UTC) - timedelta(hours=1)
    ):
        state = "failed"
    return BriefingRead.model_validate(
        {
            "briefing": artifact,
            "refresh": {
                "expected_cutoff": cutoff,
                "state": state,
                "stale": artifact is None or artifact.window_end < cutoff,
            },
        }
    )
