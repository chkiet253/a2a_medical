# server/routes/diagnose.py
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse
from server.modules.diagnose_adapter import get_agent_diagnose
from server.logger import logger

router = APIRouter()

@router.post("/diagnose")
async def diagnose(query: str = Form(...)):
    try:
        logger.info(f"[diagnose] query: {query}")
        agent = get_agent_diagnose()
        result = agent.answer(query)  # {disease, rationale, answer_raw, contexts, model}
        logger.info("[diagnose] ok")
        return result
    except Exception as e:
        logger.exception("diagnose error")
        return JSONResponse(status_code=500, content={"error": str(e)})
