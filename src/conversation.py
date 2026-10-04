from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str
    content: str


class ConversationHistory:
    def __init__(self, max_messages: int = 10) -> None:
        self.messages: list[ChatMessage] = []
        self.max_messages = max_messages

    def add_user_message(self, content: str) -> None:
        self.messages.append(
            ChatMessage(
                role="user",
                content=content,
            )
        )

        self._trim()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(
            ChatMessage(
                role="assistant",
                content=content,
            )
        )

        self._trim()

    def get_messages(self) -> list[ChatMessage]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages.clear()

    def _trim(self) -> None:
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[
                -self.max_messages:
            ]

    def format_history(self) -> str:
        if not self.messages:
            return "No previous conversation."

        return "\n".join(
            f"{message.role.capitalize()}: {message.content}"
            for message in self.messages
        )