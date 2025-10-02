from fastapi import APIRouter
from pydantic import BaseModel
from host import handle_user_message, handle_submit

router = APIRouter()

class UserMessage(BaseModel):
    text: str

class SubmitPayload(BaseModel):
    kind: str
    values: dict

@router.post("/api/message")
async def handle_message(msg: UserMessage):
    return handle_user_message(msg.text)

@router.post("/api/submit")
async def handle_submit_api(payload: SubmitPayload):
    return handle_submit(payload.kind, payload.values)
