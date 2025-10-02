import json
import logging
from typing import AsyncIterable, Union

from common.server.task_manager import InMemoryTaskManager
from agent import BookingAgent
from common.types import (
    SendTaskRequest,
    TaskSendParams,
    Message,
    TaskStatus,
    Artifact,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TextPart,
    DataPart,
    TaskState,
    Task,
    SendTaskResponse,
    InternalError,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
)
import common.server.utils as utils

logger = logging.getLogger(__name__)

class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, agent: BookingAgent):
        super().__init__()
        self.agent = agent

    async def _stream_generator(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            async for item in self.agent.stream(query, task_send_params.sessionId):
                is_task_complete = item["is_task_complete"]
                artifacts = None

                if not is_task_complete:
                    task_state = TaskState.WORKING
                    parts = [TextPart(text=item["updates"])]
                else:
                    content = item["content"]

                    # Nếu agent trả kết quả báo thiếu thông tin => tạo form artifact
                    if isinstance(content, str) and "MISSING_INFO" in content:
                        task_state = TaskState.INPUT_REQUIRED
                        form_artifact = Artifact(
                            name="booking_form",
                            description="Form đặt lịch khám",
                            parts=[
                                DataPart(
                                    data={
                                        "type": "form",
                                        "title": "Đặt lịch khám",
                                        "fields": [
                                            {"id": "HoTen", "label": "Họ và tên", "type": "text", "required": True},
                                            {"id": "Ngay", "label": "Ngày khám", "type": "date", "required": True},
                                            {"id": "Gio", "label": "Giờ khám", "type": "time", "required": True},
                                            {"id": "Email", "label": "Email liên hệ", "type": "email", "required": True},
                                        ]
                                    }
                                )
                            ],
                            index=0,
                            append=False,
                        )
                        artifacts = [form_artifact]
                        parts = []   # ⚡ bỏ text note

                    else:
                        task_state = TaskState.COMPLETED
                        parts = [TextPart(text=content)]

                        artifacts = [
                            Artifact(parts=parts, index=0, append=False)
                        ]

                message = Message(role="agent", parts=parts)
                task_status = TaskStatus(state=task_state, message=message)
                await self._update_store(task_send_params.id, task_status, artifacts)

                # Trạng thái update
                yield SendTaskStreamingResponse(
                    id=request.id,
                    result=TaskStatusUpdateEvent(id=task_send_params.id, status=task_status, final=False),
                )

                # Artifact update (nếu có)
                if artifacts:
                    for artifact in artifacts:
                        yield SendTaskStreamingResponse(
                            id=request.id,
                            result=TaskArtifactUpdateEvent(id=task_send_params.id, artifact=artifact),
                        )

                # Nếu task hoàn tất => gửi trạng thái cuối
                if is_task_complete:
                    yield SendTaskStreamingResponse(
                        id=request.id,
                        result=TaskStatusUpdateEvent(
                            id=task_send_params.id,
                            status=TaskStatus(state=task_status.state),
                            final=True,
                        ),
                    )
        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            yield JSONRPCResponse(
                id=request.id,
                error=InternalError(message="An error occurred while streaming the response"),
            )

    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ) -> None:
        task_send_params: TaskSendParams = request.params
        if not utils.are_modalities_compatible(
            task_send_params.acceptedOutputModes, BookingAgent.SUPPORTED_CONTENT_TYPES
        ):
            logger.warning(
                "Unsupported output mode. Received %s, Support %s",
                task_send_params.acceptedOutputModes,
                BookingAgent.SUPPORTED_CONTENT_TYPES,
            )
            return utils.new_incompatible_types_error(request.id)

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        error = self._validate_request(request)
        if error:
            return error
        await self.upsert_task(request.params)
        return await self._invoke(request)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error:
            return error
        await self.upsert_task(request.params)
        return self._stream_generator(request)

    async def _update_store(
        self, task_id: str, status: TaskStatus, artifacts: list[Artifact]
    ) -> Task:
        async with self.lock:
            try:
                task = self.tasks[task_id]
            except KeyError:
                logger.error(f"Task {task_id} not found for updating the task")
                raise ValueError(f"Task {task_id} not found")
            task.status = status
            if artifacts is not None:
                if task.artifacts is None:
                    task.artifacts = []
                task.artifacts.extend(artifacts)
            return task

    async def _invoke(self, request: SendTaskRequest) -> SendTaskResponse:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            result = await self.agent.invoke(query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"Error invoking agent: {e}")
            raise ValueError(f"Error invoking agent: {e}")

        # Nếu còn thiếu dữ liệu => trả form artifact
        if "MISSING_INFO" in result:
            parts = [
                DataPart(
                    data={
                        "type": "form",
                        "title": "Đặt lịch khám",
                        "fields": [
                            {"id": "HoTen", "label": "Họ và tên", "type": "text", "required": True},
                            {"id": "Ngay", "label": "Ngày khám", "type": "date", "required": True},
                            {"id": "Gio", "label": "Giờ khám", "type": "time", "required": True},
                            {"id": "Email", "label": "Email liên hệ", "type": "email", "required": True},
                        ],
                    }
                )
            ]
            task_state = TaskState.INPUT_REQUIRED
            artifacts = [Artifact(parts=parts, index=0, append=False)]
        else:
            parts = [TextPart(text=result)]
            task_state = TaskState.COMPLETED
            artifacts = [Artifact(parts=parts)]

        task = await self._update_store(
            task_send_params.id,
            TaskStatus(state=task_state, message=Message(role="agent", parts=parts)),
            artifacts,
        )
        return SendTaskResponse(id=request.id, result=task)

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        part = task_send_params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text
