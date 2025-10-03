from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# Hỗ trợ import 2 cách
try:
    from .host import HostBridge
except Exception:
    from host import HostBridge

api_router = APIRouter()
bridge = HostBridge()

class Patient(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    history: Optional[str] = None

class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)
    patient: Optional[Patient] = None
    mode: Optional[str] = Field("orchestrate", description="orchestrate|diagnose|schedule|cost")

@api_router.get("/agents")
async def list_agents():
    return await bridge.list_remote_agents()

@api_router.post("/chat")
async def chat(inp: ChatIn):
    try:
        return await bridge.send_message(
            inp.message,
            patient=inp.patient.dict() if inp.patient else None,
            mode=inp.mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Additional endpoints for backwards compatibility with other UIs
#
# The front‑end located in ``main.js``, ``form.js`` and ``options.js`` uses
# ``/api/message`` and ``/api/submit`` instead of ``/api/chat``.  To support
# those existing clients without requiring changes on the front‑end side, we
# provide thin wrappers that delegate to the underlying HostBridge.  These
# endpoints accept simple JSON payloads and forward them to the host
# service via ``bridge.send_message`` and ``bridge.send_task``.

class MessageIn(BaseModel):
    """Input model for the /api/message endpoint.

    The property name ``text`` is chosen to align with the front‑end in
    ``main.js`` which posts ``{ text: msg }``.  Only the text is used
    when forwarding to the host service; any additional fields are ignored.
    """

    text: str = Field(..., description="The raw chat message from the user")


class SubmitIn(BaseModel):
    """Input model for the /api/submit endpoint.

    A submission consists of a ``kind`` string identifying the remote agent
    or task type and a ``values`` dictionary containing arbitrary payload
    fields.  This model matches the structure used in ``form.js`` and
    ``options.js`` on the front‑end.
    """

    kind: str = Field(..., description="Identifier for the task or remote agent")
    values: Dict[str, Any] = Field({}, description="Payload values for the task")


@api_router.post("/message")
async def message(inp: MessageIn):
    """Proxy a simple chat message to the HostAgent.

    This endpoint exists for backward compatibility with older UI code that
    posts to ``/api/message`` instead of ``/api/chat``.  It takes a JSON
    object with a single ``text`` field and forwards the text to the
    HostAgent via ``bridge.send_message``.  Any exceptions are converted
    into HTTP 500 responses.
    """
    try:
        return await bridge.send_message(inp.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/submit")
async def submit(inp: SubmitIn):
    """Proxy a form or option submission to the HostAgent.

    The ``kind`` field determines which remote agent or task the payload
    corresponds to, and the ``values`` field carries the actual data.
    See the front‑end implementation in ``form.js`` and ``options.js`` for
    how this endpoint is used.
    """
    try:
        return await bridge.send_task(agent=inp.kind, payload=inp.values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/schedule")
async def schedule_task(inp: Dict[str, Any]):
    # expected: patient, preferred_date, specialty, note
    return await bridge.send_task(agent="schedule_agent", payload=inp)

@api_router.post("/cost")
async def cost_task(inp: Dict[str, Any]):
    # expected: items (list[str]) hoặc free_text
    return await bridge.send_task(agent="cost_agent", payload=inp)

@api_router.post("/history")
async def update_history(inp: Dict[str, Any]):
    return {"ok": True, "stored": inp}
