"""Self-contained chat layer: the ``Chat`` facade plus its collaborators —
``Factory`` (build the chat model / prompt / variables), ``Invoke`` (run the
model, structured or raw) and ``Adapter`` (normalize the result into
``ChatResponse``) — all as static-method classes used by ``Chat``.

``Chat`` is bound to one already-built chat model and stops at ``ChatResponse``;
turning it into an agent-level result is the caller's job.
"""
from dataclasses import dataclass
from typing import Any, Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import Config
from core.error import ValidationError
from domain.chat.mock_chat import MockChatModel
from domain.models.chat import ChatFallbackRawResponseSchema, ChatModelName, ChatModelResponseSchema


@dataclass
class ChatResponse:
    """One normalized chat invocation: the parsed payload, the token usage and
    any structured-output parsing error. ``raw`` keeps the provider message for
    debugging/traces — callers use the extracted token fields, not ``raw`` — so
    the LangChain type never leaks past this layer."""
    response_schema: ChatModelResponseSchema | None
    raw: AIMessage
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    parsing_error: Exception | None = None


class Factory:
    """Builds the chat model (per provider) and the prompt / variables."""

    @staticmethod
    def create_chat_client(config: Config, model: ChatModelName, temperature: float) -> BaseChatModel:
        """Create a chat model client for the given model name and temperature."""
        for predicate, build in Factory._client_builders():
            if predicate(model):
                return build(model, temperature, config)
        raise ValueError(f"Unsupported LLM model: {model}")

    @staticmethod
    def create_chat_message(system_prompt: str) -> ChatPromptTemplate:
        """Create the chat prompt template for the given system prompt."""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{context}{message}"),
        ])

    @staticmethod
    def create_chat_variables(message: str, context: str | None) -> dict[str, str]:
        return {"message": message, "context": context or ""}

    @staticmethod
    def _client_builders() -> list[tuple[Callable[[ChatModelName], bool], Callable[..., BaseChatModel]]]:
        return [
            (ChatModelName.is_mock, Factory._build_mock),
            (ChatModelName.is_ollama, Factory._build_ollama),
            (ChatModelName.is_openai, Factory._build_openai),
            (ChatModelName.is_anthropic, Factory._build_anthropic),
            (ChatModelName.is_other_llm_provider, Factory._build_other_llm_provider),
        ]

    @staticmethod
    def _build_mock(model: ChatModelName, temperature: float, config: Config) -> BaseChatModel:
        return MockChatModel()

    @staticmethod
    def _build_ollama(model: ChatModelName, temperature: float, config: Config) -> BaseChatModel:
        return ChatOllama(
            model=model,
            base_url=config.ollama_url,
            temperature=temperature,
            num_predict=config.ollama_num_predict,
            keep_alive=config.ollama_keep_alive,
            api_key=config.ollama_api_key,
        )

    @staticmethod
    def _build_openai(model: ChatModelName, temperature: float, config: Config) -> BaseChatModel:
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured.")
        return ChatOpenAI(model=model, api_key=config.openai_api_key, temperature=temperature)

    @staticmethod
    def _build_anthropic(model: ChatModelName, temperature: float, config: Config) -> BaseChatModel:
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured.")
        return ChatAnthropic(model=model, api_key=config.anthropic_api_key, temperature=temperature)

    @staticmethod
    def _build_other_llm_provider(model: ChatModelName, temperature: float, config: Config) -> BaseChatModel:
        if not config.other_llm_provider_api_key:
            raise ValueError("OTHER_LLM_PROVIDER_API_KEY not configured.")
        return ChatOpenAI(
            model=model,
            api_key=config.other_llm_provider_api_key,
            temperature=temperature,
            base_url=config.other_llm_provider_url,
        )


class Adapter:
    """Normalizes a raw chat invocation into a ``ChatResponse``."""

    @staticmethod
    def to_chat_response_dict(chat_response: dict[str, Any]) -> ChatResponse:
        if not isinstance(chat_response, dict):
            raise ValidationError(f"Invalid chat response format: {chat_response}")
        return Adapter._build(chat_response.get("parsed"), chat_response.get("raw"), chat_response.get("parsing_error"))

    @staticmethod
    def to_chat_response_ai_message(chat_response: AIMessage) -> ChatResponse:
        response_schema = ChatFallbackRawResponseSchema(response=str(chat_response.content))
        return Adapter._build(response_schema, chat_response, None)

    @staticmethod
    def _build(response_schema: ChatModelResponseSchema | None, raw: AIMessage | None, parsing_error: Exception | None) -> ChatResponse:
        """Assemble a ChatResponse, extracting the token usage from the provider
        message here so the LangChain ``usage_metadata`` stays inside this layer."""
        usage = (raw.usage_metadata if raw is not None else None) or {}
        return ChatResponse(
            response_schema=response_schema,
            raw=raw,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            parsing_error=parsing_error,
        )


class Invoke:
    """Runs the chat model — structured (with a response schema) or raw."""

    @staticmethod
    def invoke_without_response_schema(chat_model: BaseChatModel, chat_message: ChatPromptTemplate, chat_variables: dict[str, str]) -> ChatResponse:
        runnable = chat_message | chat_model
        chat_response: AIMessage = runnable.invoke(chat_variables)
        return Adapter.to_chat_response_ai_message(chat_response)

    @staticmethod
    def invoke_with_response_schema(chat_model: BaseChatModel, response_schema: type[ChatModelResponseSchema], label: str, chat_message: ChatPromptTemplate, chat_variables: dict[str, str]) -> ChatResponse:
        structured = chat_model.with_structured_output(response_schema, include_raw=True)
        runnable = chat_message | structured
        chat_response = runnable.invoke(chat_variables)
        normalized = Adapter.to_chat_response_dict(chat_response)
        if normalized.response_schema is None:
            raise ValidationError(f"Structured output parsing failed for '{label}': {normalized.parsing_error}")
        return normalized


class Chat:
    """Chat facade bound to one chat model."""

    def __init__(self, chat_model: BaseChatModel):
        self._chat_model = chat_model

    def invoke(
        self,
        system_prompt: str,
        message: str,
        context: str | None = None,
        response_schema: type[ChatModelResponseSchema] | None = None,
        label: str = "",
    ) -> ChatResponse:
        """Run the chat model on ``system_prompt`` + ``message`` (+ ``context``).
        With a ``response_schema`` the output is parsed as structured; otherwise a
        raw fallback is returned. ``label`` names the caller in parse errors."""
        chat_message = Factory.create_chat_message(system_prompt)
        chat_variables = Factory.create_chat_variables(message, context)
        if response_schema is None:
            return Invoke.invoke_without_response_schema(self._chat_model, chat_message, chat_variables)
        return Invoke.invoke_with_response_schema(self._chat_model, response_schema, label, chat_message, chat_variables)
