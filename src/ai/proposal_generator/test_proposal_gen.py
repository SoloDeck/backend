from fastapi import FastAPI

from src.ai.proposal_generator.api.router import router

app = FastAPI()

app.include_router(router)
