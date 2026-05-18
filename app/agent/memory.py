"""Conversation memory configuration for multi-turn chat sessions."""

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory


# In-memory store placeholder; replace with Redis/DB in production
_session_store: dict[str, BaseChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """Return or create chat message history for the given session."""
    pass  # TODO: create InMemoryChatMessageHistory if session_id not in _session_store


def get_conversation_memory(session_id: str) -> BaseChatMessageHistory:
    """Alias for session history used by the agent executor."""
    pass  # TODO: return get_session_history(session_id)


def wrap_with_message_history(runnable) -> RunnableWithMessageHistory:
    """Wrap agent runnable with RunnableWithMessageHistory for session persistence."""
    pass  # TODO: RunnableWithMessageHistory(runnable, get_session_history, input_messages_key=..., history_messages_key=...)
