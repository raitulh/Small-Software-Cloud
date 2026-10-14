from contextlib import asynccontextmanager
import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings

try:
    from arq.connections import RedisSettings, create_pool
    HAVE_ARQ = True
except ImportError:
    RedisSettings = None
    create_pool = None
    HAVE_ARQ = False

from app.routes import auth, dashboard, deployments, env_vars, health, organizations, projects, services, usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("smallcloud.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if HAVE_ARQ and create_pool is not None and RedisSettings is not None:
        try:
            app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            logger.info("Initialized shared Arq Redis connection pool")
        except Exception as exc:
            logger.warning("Could not connect to Redis during startup: %s", exc)
            app.state.arq_pool = None
    else:
        app.state.arq_pool = None
    yield
    if getattr(app.state, "arq_pool", None) is not None:
        try:
            await app.state.arq_pool.aclose()
            logger.info("Closed Arq Redis connection pool")
        except Exception as exc:
            logger.warning("Error closing Arq Redis pool: %s", exc)


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Developer-first small software cloud control plane",
    docs_url="/docs" if settings.cloud_env != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.cloud_env != "production" else None,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-Organization-ID"]
)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/v1/auth") else "private, no-cache"
    logger.info("method=%s path=%s status=%s duration_ms=%.2f request_id=%s", request.method, request.url.path, response.status_code, (time.perf_counter()-start)*1000, request_id)
    return response

app.include_router(health.router)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(organizations.router, prefix=settings.api_v1_prefix)
app.include_router(projects.router, prefix=settings.api_v1_prefix)
app.include_router(services.router, prefix=settings.api_v1_prefix)
app.include_router(env_vars.router, prefix=settings.api_v1_prefix)
app.include_router(deployments.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(usage.router, prefix=settings.api_v1_prefix)

@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.2.0",
        "docs": "/docs" if settings.cloud_env != "production" else None,
        "deployment_driver": settings.deployment_driver,
        "message": "Control plane ready. Mock deployments do not run customer code."
    }
