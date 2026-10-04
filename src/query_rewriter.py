from langchain_core.messages import HumanMessage, SystemMessage

from conversation import ConversationHistory
from llm import get_llm


def rewrite_query(
    question: str,
    history: ConversationHistory,
) -> str:
    """
    Rewrite a follow-up question into a standalone retrieval query.
    """

    messages = history.get_messages()

    if not messages:
        return question

    conversation = history.format_history()

    system_prompt = """
You rewrite conversational questions into standalone search queries.

Your job is only to rewrite the user's latest question so that it can
be understood without conversation history.

Rules:
- Preserve the user's original meaning.
- Resolve pronouns and references using the conversation history.
- Do not answer the question.
- Do not add unrelated information.
- If the question is already standalone, return it unchanged.
- Return only the rewritten question.
""".strip()

    user_prompt = f"""
Conversation history:

{conversation}

Latest question:

{question}

Rewrite the latest question as a standalone search query.
""".strip()

    llm = get_llm()

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    rewritten_query = str(response.content).strip()

    if not rewritten_query:
        return question

    return rewritten_query