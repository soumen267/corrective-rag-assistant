from conversation import ConversationHistory
from rag_graph import ask_with_graph


def main() -> None:
    history = ConversationHistory(
        max_messages=10,
    )

    while True:
        question = input(
            "\nQuestion: "
        ).strip()

        if question.lower() in {
            "exit",
            "quit",
        }:
            break

        if not question:
            continue

        answer, citations = ask_with_graph(
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
                    f"[Source {index}] "
                    f"{citation.source}"
                )


if __name__ == "__main__":
    main()