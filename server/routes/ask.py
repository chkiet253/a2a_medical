# server/routes/ask.py
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse
from host.host_agent import get_host

router = APIRouter()

@router.post("/ask")
async def ask(query: str = Form(...)):
    try:
        resp = get_host().route(query)
        return resp.model_dump()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
