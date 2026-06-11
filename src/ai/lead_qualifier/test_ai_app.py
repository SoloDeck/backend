from fastapi import FastAPI

from src.ai.lead_qualifier.api.router import router

app = FastAPI()

app.include_router(router)