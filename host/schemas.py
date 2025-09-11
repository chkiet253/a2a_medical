from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class Message(BaseModel):
    role: str
    content: str

class OrchestrateReq(BaseModel):
    # intent: symptom_advice | cost_advice | booking
    intent: str
    messages: List[Message]
    options: Optional[Dict[str, Any]] = None

class OrchestrateResp(BaseModel):
    ok: bool
    result: Dict[str, Any]
    trace: List[Dict[str, Any]]
