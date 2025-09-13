from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from server.middlewares.exception_handlers import catch_exception_middleware
from server.routes.diagnose import router as diagnose_router  # NEW
# (có thể bỏ 2 route cũ nếu không dùng nữa)
# from routes.upload_pdfs import router as upload_router
# from routes.ask_question import router as ask_router

app = FastAPI(title="Medical Diagnose API", description="A2A Medical Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(catch_exception_middleware)


# Routers
app.include_router(diagnose_router)   # NEW
# app.include_router(upload_router)
# app.include_router(ask_router)

@app.get("/health")
def health():
    return {"status":"ok"}