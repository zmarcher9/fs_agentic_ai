"""System prompt and few-shot prompt templates for the FireMapSim assistant agent."""

from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate, MessagesPlaceholder


SYSTEM_PROMPT = """You are a helpful wildfire simulation assistant for farmers and land managers.
You help users describe fire scenarios in plain language, translate locations to simulation
coordinates, configure FireMapSim runs, execute simulations, and explain results clearly.
Always confirm ambiguous locations or parameters before running expensive simulations."""


FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    # TODO: add user/assistant example pairs for coordinate + parameter extraction
]


def get_few_shot_prompt() -> FewShotChatMessagePromptTemplate:
    """Build few-shot examples block from FEW_SHOT_EXAMPLES."""
    pass  # TODO: FewShotChatMessagePromptTemplate.from_examples(...)


def get_agent_prompt() -> ChatPromptTemplate:
    """Assemble full chat prompt: system, few-shot, history, and user input."""
    pass  # TODO: ChatPromptTemplate.from_messages([
    #   ("system", SYSTEM_PROMPT),
    #   few_shot,
    #   MessagesPlaceholder("chat_history"),
    #   ("human", "{input}"),
    #   MessagesPlaceholder("agent_scratchpad"),
    # ])
