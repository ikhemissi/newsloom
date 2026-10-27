"""Request-owned Agent Framework execution and bounded, nonpersistent A2A tasks."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextvars import Context
from dataclasses import dataclass
from typing import Literal, Never, Protocol, overload
from uuid import UUID, uuid4

from a2a.auth.user import User
from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import Event, EventQueue
from a2a.server.request_handlers import RequestHandler
from a2a.server.routes.common import ServerCallContextBuilder
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.errors import (
    InvalidParamsError,
    TaskNotCancelableError,
    TaskNotFoundError,
    UnsupportedOperationError,
)
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    Content,
    ResponseStream,
    ServiceSessionId,
)
from agent_framework import Message as FrameworkMessage
from agent_framework.a2a import A2AExecutor
from newsloom_core.diagnostics import event
from starlette.requests import Request

from newsloom_agent.auth import Authorization, current_authorization, request_authorization
from newsloom_agent.delegation import DelegatedRead, remaining
from newsloom_agent.generation import MAX_OUTPUT_BYTES, GenerationStats, NewsGenerator
from newsloom_agent.models import AgentFailure
from newsloom_agent.telemetry import AgentObserver

MAX_TEXT_BYTES = 16 * 1024
MAX_TASKS = 64
TASK_RETENTION_SECONDS = 300
MAX_STREAM_EVENTS = 8


class RecentReader(Protocol):
    async def recent(self, authorization: Authorization) -> DelegatedRead: ...


class VerifiedUser(User):
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return "verified-user"


class PrivateContextBuilder(ServerCallContextBuilder):
    def build(self, request: Request) -> ServerCallContext:
        if request_authorization(request.scope) is not current_authorization():
            raise AgentFailure("missing_authorization")
        # Identity and credentials never enter SDK-serializable context state.
        return ServerCallContext(user=VerifiedUser(), state={"headers": {"a2a-version": "1.0"}})


class RecentAgent:
    id = "recent-news-access"
    name: str | None = "Recent news access"
    description: str | None = "One delegated stored-news read; no generation or research."

    def __init__(
        self,
        reader: RecentReader,
        authorization: Authorization,
        generator: NewsGenerator | None = None,
    ) -> None:
        self.reader, self.authorization = reader, authorization
        self.generator = generator
        self.stats = GenerationStats()
        self.receipt: str | None = None
        self.failure_category = "agent_execution_failed"

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> Awaitable[AgentResponse[None]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[None]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> Awaitable[AgentResponse[None]] | ResponseStream[AgentResponseUpdate, AgentResponse[None]]:
        if stream:
            return ResponseStream(self.updates(), finalizer=AgentResponse[None].from_updates)
        return self.response()

    async def read(self) -> DelegatedRead:
        try:
            remaining(self.authorization)
            async with asyncio.timeout_at(self.authorization.deadline):
                result = await self.reader.recent(self.authorization)
            remaining(self.authorization)
            if result.user_preserved is not True:
                raise AgentFailure("user_preservation_failed")
        except TimeoutError:
            self.failure_category = "request_timeout"
            raise AgentFailure("request_timeout") from None
        except AgentFailure as error:
            self.failure_category = str(error)
            raise
        return result

    async def response(self) -> AgentResponse[None]:
        result = await self.read()
        text = json.dumps(
            {
                "outcome": "news" if result.news.items else "empty",
                "news": result.news.model_dump(mode="json"),
                "user_preserved": True,
            },
            ensure_ascii=False,
        )
        return AgentResponse[None](
            messages=[FrameworkMessage(role="assistant", contents=[Content.from_text(text)])]
        )

    async def updates(self) -> AsyncGenerator[AgentResponseUpdate]:
        if self.generator is None:
            raise AgentFailure("streaming_not_available")
        try:
            async with asyncio.timeout_at(self.authorization.deadline):
                result = await self.read()
                message_id = str(uuid4())
                if not result.news.items:
                    yield AgentResponseUpdate(
                        role="assistant",
                        message_id=message_id,
                        contents=[Content.from_text("No recent stored news is available.")],
                    )
                else:
                    async for text in self.generator.stream(
                        result.news, self.authorization, self.stats
                    ):
                        remaining(self.authorization)
                        yield AgentResponseUpdate(
                            role="assistant",
                            message_id=message_id,
                            contents=[Content.from_text(text)],
                        )
                remaining(self.authorization)
                self.receipt = json.dumps(
                    {
                        "outcome": "news" if result.news.items else "empty",
                        "items": len(result.news.items),
                        "user_preserved": True,
                        "generated": bool(result.news.items),
                        "generation_calls": self.stats.calls,
                        "output_tokens": self.stats.output_tokens,
                    }
                )
        except TimeoutError:
            self.failure_category = "request_timeout"
            raise AgentFailure("request_timeout") from None
        except AgentFailure as error:
            self.failure_category = str(error)
            raise

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None
    ) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)


@dataclass(repr=False)
class TaskRecord:
    owner: tuple[UUID, UUID]
    task: Task
    expires_at: float
    deadline: float
    producer: asyncio.Task[object] | None = None
    cancel_requested: bool = False
    expiry: asyncio.TimerHandle | None = None


class TaskRegistry:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.records: dict[str, TaskRecord] = {}
        self.clock = clock

    def purge(self) -> None:
        now = self.clock()
        for task_id, record in tuple(self.records.items()):
            if now >= record.expires_at and record.producer is None:
                self.remove(task_id)

    def remove(self, task_id: str) -> None:
        record = self.records.pop(task_id, None)
        if record is not None and record.expiry is not None:
            record.expiry.cancel()

    def expire(self, task_id: str) -> None:
        self.purge()
        record = self.records.get(task_id)
        if record is not None and record.producer is not None:
            record.producer.cancel()
            record.producer.add_done_callback(lambda _: self.remove(task_id), context=Context())

    async def close(self) -> None:
        records = tuple(self.records.values())
        producers = [record.producer for record in records if record.producer is not None]
        for record in records:
            if record.expiry is not None:
                record.expiry.cancel()
        for producer in producers:
            producer.cancel()
        try:
            if producers:
                async with asyncio.timeout_at(max(record.deadline for record in records)):
                    results = await asyncio.gather(*producers, return_exceptions=True)
                if any(
                    isinstance(result, BaseException)
                    and not isinstance(result, asyncio.CancelledError)
                    for result in results
                ):
                    raise AgentFailure("agent_shutdown_failed")
        finally:
            self.records.clear()

    def owned(self, task_id: str, authorization: Authorization) -> TaskRecord:
        self.purge()
        record = self.records.get(task_id)
        if record is None or record.owner != self.owner(authorization):
            raise TaskNotFoundError()
        return record

    @staticmethod
    def owner(authorization: Authorization) -> tuple[UUID, UUID]:
        return authorization.caller.tenant, authorization.caller.object_id

    def admit(self, params: SendMessageRequest, authorization: Authorization) -> TaskRecord:
        self.purge()
        remaining(authorization)
        message = params.message
        if params.tenant and params.tenant != str(authorization.caller.tenant):
            raise InvalidParamsError(message="invalid_tenant")
        if message.task_id:
            self.owned(message.task_id, authorization)
            raise UnsupportedOperationError(message="task_continuation_not_supported")
        if message.context_id and not any(
            record.task.context_id == message.context_id
            and record.owner == self.owner(authorization)
            for record in self.records.values()
        ):
            raise TaskNotFoundError()
        if (
            message.role != Role.ROLE_USER
            or not message.message_id
            or len(message.message_id) > 128
            or len(message.parts) != 1
            or message.parts[0].WhichOneof("content") != "text"
            or message.parts[0].filename
            or message.parts[0].media_type not in ("", "text/plain")
            or message.extensions
            or message.reference_task_ids
        ):
            raise InvalidParamsError(message="plain_text_message_required")
        text = message.parts[0].text
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise InvalidParamsError(message="input_text_limit")
        if text.strip() != "recent-news":
            raise UnsupportedOperationError(message="only_recent_news_supported")
        if (
            params.configuration.return_immediately
            or params.configuration.HasField("task_push_notification_config")
            or any(mode != "text/plain" for mode in params.configuration.accepted_output_modes)
        ):
            raise UnsupportedOperationError(message="unsupported_configuration")
        if not 0 <= params.configuration.history_length <= 10:
            raise InvalidParamsError(message="invalid_history_length")
        if len(self.records) >= MAX_TASKS:
            raise UnsupportedOperationError(message="task_capacity")
        task_id = str(uuid4())
        context_id = message.context_id or str(uuid4())
        incoming = Message()
        incoming.CopyFrom(message)
        incoming.task_id, incoming.context_id = task_id, context_id
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            history=[incoming],
        )
        record = TaskRecord(
            self.owner(authorization),
            task,
            self.clock() + TASK_RETENTION_SECONDS,
            authorization.deadline,
        )
        self.records[task_id] = record
        record.expiry = asyncio.get_running_loop().call_later(
            TASK_RETENTION_SECONDS, self.expire, task_id, context=Context()
        )
        return record


class TaskEvents(EventQueue):
    def __init__(
        self,
        record: TaskRecord,
        agent: RecentAgent,
        channel: asyncio.Queue[Event] | None = None,
    ) -> None:
        self.record, self.agent = record, agent
        self.channel = channel

    async def enqueue_event(self, update: Event) -> None:
        if not isinstance(update, TaskStatusUpdateEvent | TaskArtifactUpdateEvent):
            raise AgentFailure("unsupported_agent_event")
        task = self.record.task
        if update.task_id != task.id or update.context_id != task.context_id:
            raise AgentFailure("invalid_agent_event")
        if isinstance(update, TaskArtifactUpdateEvent):
            artifact = update.artifact
            if (
                len(artifact.parts) != 1
                or artifact.parts[0].WhichOneof("content") != "text"
                or not artifact.artifact_id
            ):
                raise AgentFailure("invalid_agent_artifact")
            if task.artifacts:
                stored = task.artifacts[0]
                if stored.artifact_id != artifact.artifact_id or not update.append:
                    raise AgentFailure("invalid_agent_artifact")
                text = stored.parts[0].text + artifact.parts[0].text
                if len(text.encode()) > MAX_OUTPUT_BYTES:
                    raise AgentFailure("model_output_limit")
                stored.parts[0].text = text
            else:
                if update.append or len(artifact.parts[0].text.encode()) > MAX_OUTPUT_BYTES:
                    raise AgentFailure("invalid_agent_artifact")
                task.artifacts.add().CopyFrom(artifact)
            await self.publish(update)
            return
        if update.status.state == TaskState.TASK_STATE_FAILED:
            update.status.message.CopyFrom(
                Message(
                    message_id=str(uuid4()),
                    role=Role.ROLE_AGENT,
                    task_id=task.id,
                    context_id=task.context_id,
                    parts=[Part(text=self.agent.failure_category)],
                )
            )
        if update.status.state == TaskState.TASK_STATE_COMPLETED and self.agent.receipt is not None:
            update.status.message.CopyFrom(
                Message(
                    message_id=str(uuid4()),
                    role=Role.ROLE_AGENT,
                    task_id=task.id,
                    context_id=task.context_id,
                    parts=[Part(text=self.agent.receipt)],
                )
            )
        elif (
            update.status.state == TaskState.TASK_STATE_COMPLETED
            and not update.status.HasField("message")
            and task.history
            and task.history[-1].role == Role.ROLE_AGENT
        ):
            update.status.message.CopyFrom(task.history[-1])
        task.status.CopyFrom(update.status)
        if update.status.HasField("message") and (
            not task.history or task.history[-1].message_id != update.status.message.message_id
        ):
            task.history.add().CopyFrom(update.status.message)
        await self.publish(update)

    async def publish(self, update: Event) -> None:
        if self.channel is not None:
            async with asyncio.timeout_at(self.record.deadline):
                await self.channel.put(update)


class AgentHandler(RequestHandler):
    def __init__(
        self,
        reader: RecentReader,
        registry: TaskRegistry,
        generator: NewsGenerator | None = None,
        observer: AgentObserver | None = None,
    ) -> None:
        self.reader, self.registry = reader, registry
        self.generator = generator
        self.observer = observer

    async def on_message_send(self, params: SendMessageRequest, context: ServerCallContext) -> Task:
        authorization = current_authorization()
        record = self.registry.admit(params, authorization)
        await self.execute(params, context, record, authorization)
        return self.snapshot(
            record,
            params.configuration.history_length
            if params.configuration.HasField("history_length")
            else 2,
        )

    async def execute(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
        record: TaskRecord,
        authorization: Authorization,
        channel: asyncio.Queue[Event] | None = None,
    ) -> None:
        record.producer = asyncio.current_task()
        if record.producer is not None:
            authorization.producers.add(record.producer)
        agent = RecentAgent(self.reader, authorization, self.generator)
        execution = SendMessageRequest()
        execution.CopyFrom(params)
        execution.message.CopyFrom(record.task.history[0])
        started = time.monotonic()
        try:
            await A2AExecutor(agent, stream=self.generator is not None).execute(
                RequestContext(
                    call_context=context,
                    request=execution,
                    task_id=record.task.id,
                    context_id=record.task.context_id,
                    task=record.task,
                ),
                TaskEvents(record, agent, channel),
            )
            producer = asyncio.current_task()
            if producer is not None and producer.cancelling() and not record.cancel_requested:
                raise asyncio.CancelledError
        except TimeoutError:
            record.task.status.CopyFrom(
                TaskStatus(
                    state=TaskState.TASK_STATE_FAILED,
                    message=Message(role=Role.ROLE_AGENT, parts=[Part(text="request_timeout")]),
                )
            )
        finally:
            if record.producer is not None:
                authorization.producers.discard(record.producer)
            record.producer = None
            if (
                time.monotonic() >= authorization.deadline
                and not record.cancel_requested
                and record.task.status.state != TaskState.TASK_STATE_COMPLETED
            ):
                agent.failure_category = (
                    "authorization_expired"
                    if time.time() >= authorization.caller.expires_at
                    else "request_timeout"
                )
                record.task.status.CopyFrom(
                    TaskStatus(
                        state=TaskState.TASK_STATE_FAILED,
                        message=Message(
                            role=Role.ROLE_AGENT, parts=[Part(text=agent.failure_category)]
                        ),
                    )
                )
            if record.task.status.state in (
                TaskState.TASK_STATE_SUBMITTED,
                TaskState.TASK_STATE_WORKING,
            ):
                record.task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_CANCELED))
            outcome = (
                "success"
                if record.task.status.state == TaskState.TASK_STATE_COMPLETED
                else "cancelled"
                if record.task.status.state == TaskState.TASK_STATE_CANCELED
                else "failure"
            )
            elapsed = time.monotonic() - started
            event(
                "agent_execution",
                "",
                outcome=outcome,
                counts={"elapsed_seconds": elapsed, "generation_calls": agent.stats.calls},
            )
            if self.observer is not None:
                self.observer.execution(
                    outcome,
                    agent.failure_category if outcome == "failure" else "",
                    elapsed,
                    agent.stats,
                )

    async def on_message_send_stream(
        self, params: SendMessageRequest, context: ServerCallContext
    ) -> AsyncGenerator[Event]:
        if self.generator is None:
            raise UnsupportedOperationError(message="streaming_not_available")
        authorization = current_authorization()
        record = self.registry.admit(params, authorization)
        channel: asyncio.Queue[Event] = asyncio.Queue(maxsize=MAX_STREAM_EVENTS)
        producer = asyncio.create_task(
            self.execute(params, context, record, authorization, channel)
        )
        record.producer = producer
        authorization.producers.add(producer)

        def finished(completed: asyncio.Task[object]) -> None:
            authorization.producers.discard(completed)
            if record.producer is completed:
                record.producer = None
                record.task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_CANCELED))

        producer.add_done_callback(finished, context=Context())
        pending: asyncio.Task[Event] | None = None
        try:
            yield self.snapshot(record, 0)
            while True:
                if producer.done() and channel.empty():
                    await producer
                    yield self.snapshot(record, 0)
                    return
                pending = asyncio.create_task(channel.get())
                done, _ = await asyncio.wait(
                    (pending, producer), return_when=asyncio.FIRST_COMPLETED
                )
                if pending in done:
                    yield pending.result()
                else:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                pending = None
        finally:
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            if not producer.done():
                producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    @staticmethod
    def snapshot(record: TaskRecord, history_length: int) -> Task:
        if not 0 <= history_length <= 10:
            raise InvalidParamsError(message="invalid_history_length")
        result = Task()
        result.CopyFrom(record.task)
        result.ClearField("history")
        if history_length:
            result.history.extend(record.task.history[-history_length:])
        return result

    async def on_get_task(self, params: GetTaskRequest, context: ServerCallContext) -> Task:
        self.validate_tenant(params.tenant)
        return self.snapshot(
            self.registry.owned(params.id, current_authorization()), params.history_length
        )

    async def on_cancel_task(self, params: CancelTaskRequest, context: ServerCallContext) -> Task:
        self.validate_tenant(params.tenant)
        authorization = current_authorization()
        record = self.registry.owned(params.id, authorization)
        producer = record.producer
        if producer is None:
            raise TaskNotCancelableError()
        record.cancel_requested = True
        producer.cancel()
        try:
            async with asyncio.timeout_at(min(record.deadline, authorization.deadline)):
                results = await asyncio.gather(producer, return_exceptions=True)
        except TimeoutError:
            raise TaskNotCancelableError(message="cancellation_timeout") from None
        if any(isinstance(result, BaseException) for result in results):
            raise TaskNotCancelableError(message="cancellation_interrupted")
        return self.snapshot(record, 0)

    async def on_list_tasks(
        self, params: ListTasksRequest, context: ServerCallContext
    ) -> ListTasksResponse:
        self.validate_tenant(params.tenant)
        authorization = current_authorization()
        self.registry.purge()
        page_size = params.page_size if params.HasField("page_size") else 50
        if not 1 <= page_size <= MAX_TASKS:
            raise InvalidParamsError(message="invalid_page_size")
        if (
            params.status
            or params.history_length
            or params.include_artifacts
            or params.HasField("status_timestamp_after")
        ):
            raise UnsupportedOperationError(message="task_listing_is_metadata_only")
        records = [
            record
            for record in reversed(tuple(self.registry.records.values()))
            if record.owner == self.registry.owner(authorization)
            and (not params.context_id or record.task.context_id == params.context_id)
        ]
        if params.context_id and not records:
            raise TaskNotFoundError()
        offset = 0
        if params.page_token:
            cursor = self.registry.owned(params.page_token, authorization)
            if cursor not in records:
                raise InvalidParamsError(message="invalid_page_token")
            offset = records.index(cursor) + 1
        selected = records[offset : offset + page_size]
        tasks = [self.snapshot(record, 0) for record in selected]
        for task in tasks:
            task.status.ClearField("message")
            task.ClearField("artifacts")
        return ListTasksResponse(
            tasks=tasks,
            next_page_token=(selected[-1].task.id if offset + len(selected) < len(records) else ""),
            page_size=page_size,
            total_size=len(records),
        )

    @staticmethod
    def validate_tenant(tenant: str) -> None:
        if tenant and tenant != str(current_authorization().caller.tenant):
            raise InvalidParamsError(message="invalid_tenant")

    def unsupported_stream(
        self, params: object, context: ServerCallContext
    ) -> AsyncGenerator[Event]:
        raise UnsupportedOperationError(message="streaming_not_available")

    async def unsupported(self, params: object, context: ServerCallContext) -> Never:
        raise UnsupportedOperationError()

    on_subscribe_to_task = unsupported_stream
    on_get_extended_agent_card = unsupported
    on_create_task_push_notification_config = unsupported
    on_get_task_push_notification_config = unsupported
    on_list_task_push_notification_configs = unsupported
    on_delete_task_push_notification_config = unsupported
