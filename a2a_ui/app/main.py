from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
from .routes import router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="A2A Medical Demo")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(router)

@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
