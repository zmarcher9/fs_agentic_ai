"""
api/main.py

FastAPI wrapper for the firesim-ai agent.

Routes:
  POST /chat    — { message: str, thread_id: str } → { reply: str }
  GET  /health  — sanity check

Run locally:
  uvicorn api.main:app --reload --port 8000

Or from the project root:
  python -m uvicorn api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.agent import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("firesim-ai API starting up")
    yield
    logger.info("firesim-ai API shutting down")


app = FastAPI(
    title="firesim-ai",
    description="Agentic setup co-pilot for FireMapSim wildfire simulations",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's natural-language input")
    thread_id: str = Field(..., min_length=1, description="Conversation thread identifier")


class ChatResponse(BaseModel):
    reply: str


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    """Quick sanity check — confirms the API process is alive."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/chat", response_model=ChatResponse, tags=["agent"])
async def chat(req: ChatRequest):
    """
    Send a message to the firesim-ai agent and get a reply.

    - **message**: natural-language input from the user / demo script
    - **thread_id**: stable ID for the conversation; the agent's MemorySaver
      uses this to maintain context across turns
    """
    logger.info("thread=%s | user: %s", req.thread_id, req.message[:120])

    try:
        reply = run_agent(
            user_message=req.message,
            thread_id=req.thread_id,
        )
    except Exception as exc:
        logger.exception("Agent error on thread=%s", req.thread_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("thread=%s | agent: %s", req.thread_id, reply[:120])
    return ChatResponse(reply=reply)
