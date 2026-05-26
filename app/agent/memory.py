"""Conversation memory helpers for FireMapSim agent sessions."""

from langchain.memory import ConversationBufferWindowMemory


def get_memory() -> ConversationBufferWindowMemory:
    """Return a fresh memory object that keeps only the last 10 messages."""
    return ConversationBufferWindowMemory(
        memory_key="chat_history",
        return_messages=True,
        k=10,
    )
