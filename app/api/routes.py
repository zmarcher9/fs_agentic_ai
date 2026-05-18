"""FastAPI route handlers for the conversational chat interface."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agent.agent import get_agent_executor
from app.config import Settings, get_settings

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    """Incoming chat message from a client."""

    message: str = Field(..., description="User message in natural language")
    session_id: str | None = Field(default=None, description="Optional conversation session id")


class ChatResponse(BaseModel):
    """Agent reply returned to the client."""

    reply: str = Field(..., description="Human-readable assistant response")
    session_id: str = Field(..., description="Conversation session id for follow-up turns")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """Accept a user message, run the agent, and return the assistant reply."""
    pass  # TODO: invoke agent executor with request.message and memory keyed by session_id


@router.get("/chat/sessions/{session_id}")
async def get_session_history(session_id: str) -> dict:
    """Return conversation history for a session (optional admin/debug endpoint)."""
    pass  # TODO: load memory store for session_id
