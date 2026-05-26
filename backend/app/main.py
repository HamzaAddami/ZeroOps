from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import asyncio
from app.api.routes.auth_router import auth_router
from app.api.routes.project_router import project_router
from app.api.routes.user_router import user_router
from app.api.routes.vm_request_router import vm_router
from app.core.db import test_connection


app = FastAPI(version='0.1.0')

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX="/api/v1"
app.include_router(project_router, prefix=PREFIX)
app.include_router(user_router, prefix=PREFIX)
app.include_router(auth_router, prefix=PREFIX)
app.include_router(vm_router, prefix=PREFIX)

@app.get("/")
async def root():
    return {"message": "Welcome to ZeroOps"}
@app.get("/test-DB-connection")
async def get_db_connection_health():
    return {"message": f"{test_connection()}"}

@app.get("/health")
async def get_health():
    return {"status": "ok"}


