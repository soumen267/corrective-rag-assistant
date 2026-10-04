from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from citations import Citation, create_citations
from conversation import ConversationHistory
from hybrid_search import hybrid_search
from llm import get_llm
from query_rewriter import rewrite_query
from reranker import rerank_documents


load_dotenv()


CANDIDATE_LIMIT = 10
FINAL_LIMIT = 3


def format_context(
    documents: list[Document],
) -> str:
    """
    Format retrieved documents as numbered sources so the LLM
    can reference them using [Source N].
    """
    sections = []

    for index, document in enumerate(
        documents,
        start=1,
    ):
        source = document.metadata.get(
            "source",
            "Unknown",
        )

        page = document.metadata.get("page")

        header = (
            f"[Source {index}] "
            f"{source}"
        )

        if page is not None:
            try:
                page_number = int(page) + 1
                header += f", page {page_number}"
            except (TypeError, ValueError):
                pass

        sections.append(
            f"{header}\n"
            f"{document.page_content}"
        )

    return "\n\n---\n\n".join(sections)


def print_retrieval_debug(
    original_question: str,
    retrieval_query: str,
    search_results: list[
        tuple[Document, float]
    ],
) -> None:
    print("\n[Retrieval Debug]")
    print(f"Original: {original_question}")
    print(f"Search:   {retrieval_query}")

    if not search_results:
        print("No relevant chunks found.")
        return

    for index, (document, score) in enumerate(
        search_results,
        start=1,
    ):
        source = document.metadata.get(
            "source",
            "Unknown",
        )

        page = document.metadata.get("page")

        debug_message = (
            f"{index}. "
            f"reranker_score={score:.4f} "
            f"source={source}"
        )

        if page is not None:
            try:
                debug_message += (
                    f" page={int(page) + 1}"
                )
            except (TypeError, ValueError):
                pass

        print(debug_message)


def retrieve_documents(
    query: str,
) -> list[tuple[Document, float]]:
    """
    Retrieve candidate documents using hybrid search,
    then rerank them using the cross-encoder.
    """
    hybrid_results = hybrid_search(
        query=query,
        limit=CANDIDATE_LIMIT,
    )

    candidate_documents = [
        document
        for document, _score in hybrid_results
    ]

    if not candidate_documents:
        return []

    return rerank_documents(
        query=query,
        documents=candidate_documents,
        limit=FINAL_LIMIT,
    )


def ask(
    question: str,
    history: ConversationHistory,
) -> tuple[str, list[Citation]]:
    """
    Rewrite conversational questions, retrieve relevant
    context, generate a grounded answer, and return
    structured citations.
    """

    # Step 1: Convert a conversational question into
    # a standalone retrieval query.
    retrieval_query = rewrite_query(
        question=question,
        history=history,
    )

    # Step 2: Hybrid retrieval + reranking.
    search_results = retrieve_documents(
        query=retrieval_query,
    )

    print_retrieval_debug(
        original_question=question,
        retrieval_query=retrieval_query,
        search_results=search_results,
    )

    documents = [
        document
        for document, _score in search_results
    ]

    # Step 3: Reject the question if retrieval
    # found no relevant documents.
    if not documents:
        answer = (
            "I don't have enough information "
            "in the provided documents."
        )

        history.add_user_message(question)
        history.add_assistant_message(answer)

        return answer, []

    # Step 4: Build numbered context.
    context = format_context(documents)

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

    conversation = history.format_history()

    user_prompt = f"""
Conversation history:

{conversation}

Retrieved context:

{context}

Current question:

{question}
""".strip()

    # Step 5: Generate the grounded answer.
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

    # Step 6: Convert retrieved chunks into
    # structured citation objects.
    citations = create_citations(
        search_results
    )

    # Step 7: Store conversation history BEFORE returning.
    history.add_user_message(question)
    history.add_assistant_message(answer)

    return answer, citations


def main() -> None:
    history = ConversationHistory(
        max_messages=10,
    )

    print("=" * 60)
    print("Conversational Local RAG Assistant")
    print("=" * 60)

    print("Commands:")
    print("  exit  - stop")
    print("  clear - clear conversation history")

    while True:
        try:
            question = input(
                "\nAsk a question: "
            ).strip()

            if not question:
                continue

            if question.lower() in {
                "exit",
                "quit",
            }:
                print("\nGoodbye!")
                break

            if question.lower() == "clear":
                history.clear()

                print(
                    "\nConversation history cleared."
                )

                continue

            answer, citations = ask(
                question=question,
                history=history,
            )

            print("\nAnswer:")
            print(answer)

            if citations:
                print("\nSources:")

                for index, citation in enumerate(
                    citations,
                    start=1,
                ):
                    print(
                        f"\n[Source {index}]"
                    )

                    print(
                        f"Source: "
                        f"{citation.source}"
                    )

                    print(
                        f"File: "
                        f"{citation.file_name}"
                    )

                    if citation.page is not None:
                        print(
                            f"Page: "
                            f"{citation.page + 1}"
                        )

                    print(
                        f"Score: "
                        f"{citation.relevance_score:.4f}"
                    )

                    print(
                        f"Chunk ID: "
                        f"{citation.chunk_id}"
                    )

                    print(
                        f"Excerpt: "
                        f"{citation.excerpt}"
                    )

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break

        except Exception as exception:
            print(
                f"\nError: {exception}"
            )


if __name__ == "__main__":
    main()