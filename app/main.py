"""
Punto de entrada del mock de Brightspace. Se arranca con la fábrica create_app:

    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8800
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import seed
from app.api import dropbox, enrollments, grades, users, versions
from app.config import Settings
from app.db import init_db
from app.errors import D2LError
from app.oauth import routes as oauth_routes
from app.security.keys import load_or_create_signing_key
from app.security.ratelimit import TokenBucketLimiter
from app.security.tokens import verify_access_token


def _bearer_token(request: Request) -> str | None:
    """
    [DOC] El token va en 'Authorization: Bearer ...'. Un ejemplo de la doc de OAuth de D2L usa
    'Authentication: Bearer ...', así que el mock acepta ambos encabezados.
    """
    for header in ("authorization", "authentication"):
        value = request.headers.get(header, "")
        if value[:7].lower() == "bearer ":
            return value[7:].strip()
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    seed.seed_demo_if_empty(settings)

    # redirect_slashes=False: igual que en Brightspace, '/folders' y '/folders/' son rutas distintas.
    app = FastAPI(title="Brightspace mock (EduTrace)", redirect_slashes=False,
                  docs_url="/.mock/docs", openapi_url="/.mock/openapi.json", redoc_url=None)
    app.state.settings = settings
    app.state.signing_key = load_or_create_signing_key(settings.data_dir / "signing_key.pem")
    app.state.limiter = TokenBucketLimiter(settings.rate_limit_capacity, settings.rate_limit_window_s)

    @app.middleware("http")
    async def d2l_api_middleware(request: Request, call_next):
        """Para /d2l/api/...: lee el token (si hay) y aplica el límite de tasa por app."""
        if not request.url.path.startswith("/d2l/api/"):
            return await call_next(request)
        token = _bearer_token(request)
        claims = verify_access_token(request.app.state.signing_key, token) if token else None
        request.state.token_claims = claims
        bucket = f"app:{claims['azp']}" if claims else f"ip:{request.client.host if request.client else '-'}"
        decision = request.app.state.limiter.consume(bucket)
        if not decision.allowed:
            return PlainTextResponse("Too Many Requests", status_code=429, headers=decision.headers())
        response = await call_next(request)
        for name, value in decision.headers().items():
            response.headers[name] = value
        return response

    @app.exception_handler(D2LError)
    async def d2l_error(_: Request, exc: D2LError):
        return exc.response()

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        # 404 de ruta inexistente y 405 de método no permitido, en texto plano como la API real.
        message = "" if exc.status_code == 404 else str(exc.detail)
        return PlainTextResponse(message, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # [DOC] Si un parámetro de la ruta no se puede interpretar, la API responde 404; si falla la query, 400.
        in_path = any(err.get("loc", [None])[0] == "path" for err in exc.errors())
        return PlainTextResponse("" if in_path else "Invalid parameter", status_code=404 if in_path else 400)

    app.include_router(oauth_routes.router)
    app.include_router(versions.router)
    app.include_router(users.router)
    app.include_router(enrollments.lp)
    app.include_router(enrollments.le)
    app.include_router(dropbox.router)
    app.include_router(grades.router)
    return app

