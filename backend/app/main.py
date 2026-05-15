from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.project_router import project_router
from app.core.db import test_connection


app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router)

@app.get("/")
async def root():
    return {"message": "Welcome to ZeroOps"}
@app.get("/test-DB-connection")
async def get_db_connection_health():
    return {"message": f"{test_connection()}"}

@app.get("/health")
async def get_health():
    return {"status": "ok"}


