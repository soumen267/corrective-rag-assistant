from langchain_core.documents import Document
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from llm import get_llm


RELEVANT = "relevant"
NOT_RELEVANT = "not_relevant"


def grade_document(
    question: str,
    document: Document,
) -> bool:
    """
    Decide whether a retrieved document contains information
    relevant to answering the question.
    """
    system_prompt = """
You are a relevance grader for a RAG system.

Determine whether the retrieved document contains information
that is relevant to answering the user's question.

Rules:
- Return exactly one word: relevant or not_relevant.
- Return relevant when the document contains useful information
  for answering the question.
- Return not_relevant when the document is unrelated or does not
  contain useful information for answering the question.
- Do not answer the user's question.
- Do not explain your decision.
""".strip()

    user_prompt = f"""
Question:

{question}

Retrieved document:

{document.page_content}
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

    result = str(
        response.content
    ).strip().lower()

    return result == RELEVANT


def grade_documents(
    question: str,
    search_results: list[
        tuple[Document, float]
    ],
) -> list[tuple[Document, float]]:
    """
    Keep only documents judged relevant.
    """
    relevant_results = []

    for document, score in search_results:
        is_relevant = grade_document(
            question=question,
            document=document,
        )

        source = document.metadata.get(
            "source",
            "Unknown",
        )

        print(
            "[Document Grader] "
            f"{'RELEVANT' if is_relevant else 'NOT RELEVANT'} "
            f"source={source}"
        )

        if is_relevant:
            relevant_results.append(
                (document, score)
            )

    return relevant_results