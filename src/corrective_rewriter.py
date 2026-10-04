from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from llm import get_llm


def rewrite_for_retrieval(
    question: str,
    previous_query: str,
) -> str:
    """
    Rewrite a failed retrieval query into a more explicit
    search-oriented query.
    """
    system_prompt = """
You improve search queries for a RAG retrieval system.

The previous retrieval query did not find sufficiently relevant
documents.

Rewrite the query to improve retrieval.

Rules:
- Preserve the user's original intent.
- Make implicit technical concepts explicit when possible.
- Prefer important nouns, framework names, method names and
  technical terms.
- Do not answer the question.
- Do not invent facts that are not implied by the question.
- Return only the rewritten search query.
""".strip()

    user_prompt = f"""
Original question:

{question}

Previous search query:

{previous_query}

Create a better retrieval query.
""".strip()

    llm = get_llm()

    response = llm.invoke(
        [
            SystemMessage(
                content=system_prompt,
            ),
            HumanMessage(
                content=user_prompt,
            ),
        ]
    )

    rewritten_query = str(
        response.content
    ).strip()

    if not rewritten_query:
        return previous_query

    return rewritten_query