"""
Atlantic Highlands - Main FastAPI Application
Document library + financial analysis for town and school district.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, ALLOWED_ORIGINS, DEBUG
from database import init_db

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routes
from routes.auth import router as auth_router
from routes.documents import router as documents_router
from routes.projects import router as projects_router
from routes.financial import router as financial_router
from routes.admin import router as admin_router
from routes.scraper import router as scraper_router
from routes.chat import router as chat_router
from routes.search import router as search_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(documents_router, prefix="/api/documents", tags=["documents"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(financial_router, prefix="/api/financial", tags=["financial-analysis"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(scraper_router, prefix="/api/scraper", tags=["scraper"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(search_router, prefix="/api/search", tags=["search"])


@app.on_event("startup")
async def startup():
    init_db()
    logger.info(f"{APP_NAME} started")


@app.get("/health")
async def health():
    return {"status": "healthy", "app": APP_NAME}
