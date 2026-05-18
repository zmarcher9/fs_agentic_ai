"""FastAPI application entry point for the firesim-ai chat API."""

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="firesim-ai",
    description="Conversational interface for FireMapSim wildfire simulations",
    version="0.1.0",
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service health status for load balancers and probes."""
    pass  # TODO: return {"status": "ok", "env": settings.app_env}


def main() -> None:
    """Run the application with uvicorn when executed as a script."""
    pass  # TODO: uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.app_env == "development")


if __name__ == "__main__":
    main()
