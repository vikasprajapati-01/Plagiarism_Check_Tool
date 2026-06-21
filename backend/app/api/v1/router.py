"""Central API router — mounts all v1 sub-routers in one place."""

from fastapi import APIRouter

from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.reports import router as reports_router
from app.api.v1.compare import router as compare_router

api_router = APIRouter()

api_router.include_router(pipeline_router, prefix="/pipeline", tags=["Pipeline"])
api_router.include_router(reports_router,  prefix="/reports",  tags=["Reports"])
api_router.include_router(compare_router,  prefix="/compare",  tags=["Compare"])
