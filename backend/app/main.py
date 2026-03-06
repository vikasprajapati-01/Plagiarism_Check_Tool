from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import ingest, detect, ai_detect

app = FastAPI(title="Plagiarism Check Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Plagiarism Checker Backend Running"}

app.mount("/api/v1/ingest", ingest.app)
app.mount("/api/v1/detect", detect.app)
app.include_router(ai_detect.app, prefix="/api/v1/ai-detect", tags=["AI Detection"])