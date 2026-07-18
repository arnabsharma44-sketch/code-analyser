from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import init_db

app = FastAPI(
    title=settings.project_name,
    description="API for parsing code snippets, finding bugs, and providing drop-in fixes via OpenRouter.",
    version="1.0.0"
)

from app.core.rate_limiter import RateLimitMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    RateLimitMiddleware,
    rate_limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

init_db()
app.include_router(api_router, prefix="/api/v1")

@app.get("/", response_class=HTMLResponse)
async def homepage() -> HTMLResponse:
    return HTMLResponse(
        """
        <html>
            <head>
                <title>Code Analyser API</title>
            </head>
            <body>
                <h1>Code Analyser API</h1>
                <p>This is a backend API. Visit <a href="/api/v1/health/">/api/v1/health/</a> to check service status.</p>
                <p>API docs are available at <a href="/docs">/docs</a> and <a href="/redoc">/redoc</a>.</p>
            </body>
        </html>
        """
    )
