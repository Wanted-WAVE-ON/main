from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401 - registers SQLAlchemy metadata
from .config import PROJECT_ROOT, settings
from .database import SessionLocal, init_db
from .routers import agent, demo, health, users
from .services.demo_service import ensure_demo_user

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    (PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as db:
        ensure_demo_user(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Personalized Spatial Agent API: observation, pattern discovery, suggestion, "
        "personal gesture memory, execution, and feedback."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(agent.router, prefix=settings.api_prefix)
app.include_router(demo.router, prefix=settings.api_prefix)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
