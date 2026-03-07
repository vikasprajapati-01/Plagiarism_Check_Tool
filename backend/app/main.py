from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.ingest import app as ingest_router
from app.api.v1.detect import app as detect_router
from app.api.v1 import ai_detect

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
  
# Mount sub-apps with distinct prefixes so docs and routes are visible
app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["Ingest"])
app.include_router(detect_router, prefix="/api/v1/detect", tags=["Detect"])
app.include_router(ai_detect.app, prefix="/api/v1/ai-detect", tags=["AI Detection"])
