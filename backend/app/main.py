from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.graph.router import router as graph_router
from app.session.store import InMemorySessionStore


def create_app() -> FastAPI:
    app = FastAPI(title="Okta AIAgent Visualiser")

    # Safety net for direct-to-backend debugging; the app itself doesn't rely
    # on this because Vite proxies /api, /auth, /callback so the browser only
    # ever sees http://localhost:5173.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.session_store = InMemorySessionStore()

    app.include_router(auth_router)
    app.include_router(graph_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
