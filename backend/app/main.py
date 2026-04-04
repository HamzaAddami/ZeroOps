from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core import db

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/test-connection")
async def test_connection():
    return {"Connection " : f"{db.test_connection()}"}
