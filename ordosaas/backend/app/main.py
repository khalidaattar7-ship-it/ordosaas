"""OrdoSaaS FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.comparisons.router import router as comparisons_router
from app.config import settings
from app.database import init_db
from app.errors import AppError
from app.instances.router import router as instances_router
from app.machines.router import router as machines_router
from app.resolutions.router import router as resolutions_router
from app.tenant.router import router as tenant_router
from app.users.router import router as users_router

logger = logging.getLogger("ordosaas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="OrdoSaaS API",
    version="1.0.0",
    description=(
        "API multi-tenant d'ordonnancement de production industrielle. "
        "Importez des instances d'ateliers, résolvez-les avec plusieurs "
        "solveurs (CP-SAT, ATCS, LNS récursif par fenêtres), visualisez "
        "les plannings et comparez les performances."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=f"{API_PREFIX}/auth", tags=["auth"])
app.include_router(users_router, prefix=f"{API_PREFIX}/users", tags=["users"])
app.include_router(machines_router, prefix=f"{API_PREFIX}/machines", tags=["machines"])
app.include_router(instances_router, prefix=f"{API_PREFIX}/instances", tags=["instances"])
app.include_router(resolutions_router, prefix=f"{API_PREFIX}/resolutions", tags=["resolutions"])
app.include_router(comparisons_router, prefix=f"{API_PREFIX}/comparisons", tags=["comparisons"])
app.include_router(tenant_router, prefix=f"{API_PREFIX}/tenant", tags=["tenant"])
app.include_router(audit_router, prefix=f"{API_PREFIX}/audit-logs", tags=["audit"])


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "detail": exc.extra},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code_map = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": code_map.get(exc.status_code, "http_error"),
            "message": exc.detail if isinstance(exc.detail, str) else "Erreur",
            "detail": {} if isinstance(exc.detail, str) else exc.detail,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Données de requête invalides",
            "detail": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def internal_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "Une erreur interne est survenue.",
            "detail": {},
        },
    )


@app.get("/", tags=["system"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
