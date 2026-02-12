from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.generate import router as generate_router


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(generate_router)
    return app


app = create_app()
