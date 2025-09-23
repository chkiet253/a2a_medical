from __future__ import annotations
from typing import AsyncIterable, Union, Any
import json, logging

from common.types import (
    SendTaskRequest, TaskSendParams, Message, TaskStatus, Artifact,
    TaskStatusUpdateEvent, TaskArtifactUpdateEvent, TextPart, TaskState, Task,
    SendTaskResponse, InternalError, JSONRPCResponse,
    SendTaskStreamingRequest, SendTaskStreamingResponse,
)
from common.server.task_manager import InMemoryTaskManager
import common.server.utils as utils

logger = logging.getLogger(__name__)

class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, agent: Any):
        super().__init__()
        self.agent = agent

    async def _stream_generator(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            async for item in self.agent.stream(query, task_send_params.sessionId):
                is_task_complete = bool(item.get("is_task_complete"))
                artifacts = None
                if not is_task_complete:
                    task_state = TaskState.WORKING
                    parts = [{"type": "text", "text": item.get("updates", "")}]
                else:
                    content = item.get("content")
                    task_state = TaskState.COMPLETED
                    if isinstance(content, dict):
                        parts = [{"type": "data", "data": content}]
                    else:
                        parts = [{"type": "text", "text": str(content)}]
                    artifacts = [Artifact(parts=parts, index=0, append=False)]

                message = Message(role="agent", parts=parts)
                task_status = TaskStatus(state=task_state, message=message)
                await self._update_store(task_send_params.id, task_status, artifacts)

                yield SendTaskStreamingResponse(
                    id=request.id,
                    result=TaskStatusUpdateEvent(
                        id=task_send_params.id, status=task_status, final=False
                    ),
                )
                if artifacts:
                    for artifact in artifacts:
                        yield SendTaskStreamingResponse(
                            id=request.id,
                            result=TaskArtifactUpdateEvent(
                                id=task_send_params.id, artifact=artifact
                            ),
                        )
                if is_task_complete:
                    yield SendTaskStreamingResponse(
                        id=request.id,
                        result=TaskStatusUpdateEvent(
                            id=task_send_params.id,
                            status=TaskStatus(state=task_state),
                            final=True,
                        ),
                    )
        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            yield JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message="An error occurred while streaming the response"
                ),
            )
            return


    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ) -> None:
        task_send_params: TaskSendParams = request.params
        supported = getattr(self.agent, "SUPPORTED_CONTENT_TYPES", ["text", "text/plain"])
        if not utils.are_modalities_compatible(task_send_params.acceptedOutputModes, supported):
            logger.warning(
                "Unsupported output mode. Received %s, Support %s",
                task_send_params.acceptedOutputModes, supported,
            )
            return utils.new_incompatible_types_error(request.id)

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        error = self._validate_request(request)
        if error: return error
        await self.upsert_task(request.params)
        return await self._invoke(request)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error: return error
        await self.upsert_task(request.params)
        return self._stream_generator(request)

    async def _update_store(
        self, task_id: str, status: TaskStatus, artifacts: list[Artifact] | None
    ) -> Task:
        async with self.lock:
            task = self.tasks[task_id]
            task.status = status
            if artifacts:
                task.artifacts = (task.artifacts or []) + artifacts
            return task

    async def _invoke(self, request: SendTaskRequest) -> SendTaskResponse:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            result = await self.agent.invoke(query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"Error invoking agent: {e}")
            raise ValueError(f"Error invoking agent: {e}")
        parts = [{"type": "text", "text": result}]
        task_state = TaskState.COMPLETED
        task = await self._update_store(
            task_send_params.id,
            TaskStatus(state=task_state, message=Message(role="agent", parts=parts)),
            [Artifact(parts=parts)],
        )
        return SendTaskResponse(id=request.id, result=task)

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        part = task_send_params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text
