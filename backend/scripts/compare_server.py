"""
Lightweight server for testing just the cross-comparison endpoints.
Run: python scripts/compare_server.py
Swagger: http://127.0.0.1:8000/docs
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.compare import router

app = FastAPI(title="Cross-Comparison Test Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/compare", tags=["Compare"])

@app.get("/")
def health():
    return {"status": "running", "docs": "http://127.0.0.1:8001/docs"}

if __name__ == "__main__":
    import uvicorn
    print("Starting compare-only server...")
    print("Swagger UI: http://127.0.0.1:8001/docs")
    uvicorn.run(app, host="127.0.0.1", port=8001)
