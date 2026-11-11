import os

from langchain_ollama import ChatOllama


def get_llm() -> ChatOllama:
    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        temperature=0,
        timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
    )
