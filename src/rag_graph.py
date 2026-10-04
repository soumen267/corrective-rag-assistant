from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from citations import Citation, create_citations
from conversation import ConversationHistory
from corrective_rewriter import rewrite_for_retrieval
from document_grader import grade_documents

from llm import get_llm
from query_rewriter import rewrite_query
from rag import format_context, retrieve_documents


class RAGState(TypedDict):
    question: str
    history: ConversationHistory

    retrieval_query: str

    search_results: list[
        tuple[Document, float]
    ]

    relevant_results: list[
        tuple[Document, float]
    ]

    documents: list[Document]

    answer: str

    citations: list[Citation]

    retry_count: int
    max_retries: int


def rewrite_query_node(
    state: RAGState,
) -> dict:
    question = state["question"]
    history = state["history"]

    retrieval_query = rewrite_query(
        question=question,
        history=history,
    )

    print("\n[Graph: Query Rewrite]")
    print(f"Original: {question}")
    print(f"Search:   {retrieval_query}")

    return {
        "retrieval_query": retrieval_query,
    }


def retrieve_node(
    state: RAGState,
) -> dict:
    retrieval_query = state[
        "retrieval_query"
    ]

    search_results = retrieve_documents(
        query=retrieval_query,
    )

    print("\n[Graph: Retrieval]")
    print(
        f"Attempt: "
        f"{state['retry_count'] + 1}"
    )

    if not search_results:
        print("No chunks retrieved.")

    for index, (
        document,
        score,
    ) in enumerate(
        search_results,
        start=1,
    ):
        source = document.metadata.get(
            "source",
            "Unknown",
        )

        print(
            f"{index}. "
            f"reranker_score={score:.4f} "
            f"source={source}"
        )

    return {
        "search_results": search_results,
    }

def corrective_rewrite_node(
    state: RAGState,
) -> dict:
    old_query = state[
        "retrieval_query"
    ]

    new_query = rewrite_for_retrieval(
        question=state["question"],
        previous_query=old_query,
    )

    new_retry_count = (
        state["retry_count"] + 1
    )

    print("\n[Graph: Corrective Rewrite]")
    print(f"Old: {old_query}")
    print(f"New: {new_query}")
    print(
        f"Retry: "
        f"{new_retry_count}/"
        f"{state['max_retries']}"
    )

    return {
        "retrieval_query": new_query,
        "retry_count": new_retry_count,
        "search_results": [],
        "relevant_results": [],
        "documents": [],
    }

def grade_documents_node(
    state: RAGState,
) -> dict:
    search_results = state[
        "search_results"
    ]

    if not search_results:
        return {
            "relevant_results": [],
            "documents": [],
        }

    relevant_results = grade_documents(
        question=state["retrieval_query"],
        search_results=search_results,
    )

    documents = [
        document
        for document, _score in relevant_results
    ]

    print(
        "\n[Graph: Grading] "
        f"{len(relevant_results)}/"
        f"{len(search_results)} relevant"
    )

    return {
        "relevant_results": relevant_results,
        "documents": documents,
    }

def route_after_grading(
    state: RAGState,
) -> str:
    if state["documents"]:
        return "generate"

    if (
        state["retry_count"]
        < state["max_retries"]
    ):
        return "rewrite"

    return "fallback"


def fallback_node(
    state: RAGState,
) -> dict:
    return {
        "answer": (
            "I don't have enough information "
            "in the provided documents."
        ),
        "citations": [],
    }


def generate_node(
    state: RAGState,
) -> dict:
    question = state["question"]
    history = state["history"]
    documents = state["documents"]

    context = format_context(
        documents
    )

    conversation = history.format_history()

    system_prompt = """
You are a helpful RAG assistant.

Answer the user's question using only the provided context.

Use the conversation history only to understand the user's current
question. Factual claims in the answer must come from the retrieved
context.

Rules:
- Do not use outside knowledge.
- Do not make up information.
- Cite supporting context using [Source N].
- Use the source number exactly as provided in the context.
- Do not invent source numbers.
- If multiple sources support a statement, you may cite multiple
  sources.
- If the retrieved context does not contain enough information,
  say:
  "I don't have enough information in the provided documents."
- Keep the answer clear and concise.
""".strip()

    user_prompt = f"""
Conversation history:

{conversation}

Retrieved context:

{context}

Current question:

{question}
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

    answer = str(
        response.content
    ).strip()

    return {
        "answer": answer,
    }


def citations_node(
    state: RAGState,
) -> dict:
    citations = create_citations(
        state["relevant_results"]
    )

    return {
        "citations": citations,
    }


def build_rag_graph():
    builder = StateGraph(RAGState)

    builder.add_node(
        "rewrite_query",
        rewrite_query_node,
    )

    builder.add_node(
        "retrieve",
        retrieve_node,
    )

    builder.add_node(
        "grade_documents",
        grade_documents_node,
    )

    builder.add_node(
        "corrective_rewrite",
        corrective_rewrite_node,
    )

    builder.add_node(
        "fallback",
        fallback_node,
    )

    builder.add_node(
        "generate",
        generate_node,
    )

    builder.add_node(
        "citations",
        citations_node,
    )

    builder.add_edge(
        START,
        "rewrite_query",
    )

    builder.add_edge(
        "rewrite_query",
        "retrieve",
    )

    builder.add_edge(
        "retrieve",
        "grade_documents",
    )

    builder.add_conditional_edges(
        "grade_documents",
        route_after_grading,
        {
            "generate": "generate",
            "rewrite": "corrective_rewrite",
            "fallback": "fallback",
        },
    )

    builder.add_edge(
        "corrective_rewrite",
        "retrieve",
    )

    builder.add_edge(
        "generate",
        "citations",
    )

    builder.add_edge(
        "citations",
        END,
    )

    builder.add_edge(
        "fallback",
        END,
    )

    return builder.compile()


rag_graph = build_rag_graph()


def ask_with_graph(
    question: str,
    history: ConversationHistory,
) -> tuple[str, list[Citation]]:
    initial_state: RAGState = {
        "question": question,
        "history": history,
        "retrieval_query": "",
        "search_results": [],
        "relevant_results": [],
        "documents": [],
        "answer": "",
        "citations": [],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = rag_graph.invoke(
        initial_state
    )

    answer = result["answer"]
    citations = result["citations"]

    history.add_user_message(question)
    history.add_assistant_message(answer)

    return answer, citations