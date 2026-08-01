from domain.chat.base import Chat, Factory as ChatFactory, ChatResponse

from models.domain.chat import ChatModelName


class ChatService:

    def __init__(self):
        self._chat_clients_instances: dict[tuple[ChatModelName, float], Chat] = {}

    def ping_chat(self, model: ChatModelName, temperature: float, message: str) -> ChatResponse:
        """Ping the chat model with the given message and return the response."""
        chat = self.build_chat(model=model, temperature=temperature)
        return chat.invoke(system_prompt="", message=message)

    def list_models(self) -> list[ChatModelName]:
        """List the supported chat model identifiers."""
        return list(ChatModelName)

    def build_chat(self, model: ChatModelName, temperature: float) -> Chat:
        """Create a new chat client for the given model and temperature,
        reusing the cached instance for the same (model, temperature) pair."""
        key = (model, temperature)
        if key in self._chat_clients_instances:
            return self._chat_clients_instances[key]
        chat: Chat = ChatFactory.create_chat(model=model, temperature=temperature)
        self._chat_clients_instances[key] = chat
        return self._chat_clients_instances[key]
