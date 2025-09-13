
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from server.routes import ask, diagnose

app = FastAPI(title="A2A Hospital Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,     # <- bool, không phải list
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask.router)
app.include_router(diagnose.router)

@app.get("/health")
def health():
    return {"status": "ok"}
