"""Self-contained chat layer: the ``Chat`` facade plus its collaborators —
``Factory`` (build the chat model / prompt / variables), ``Invoke`` (run the
model, structured or raw) and ``Adapter`` (normalize the result into
``ChatResponse``) — all as static-method classes used by ``Chat``.

``Chat`` is bound to one already-built chat model and stops at ``ChatResponse``;
turning it into an agent-level result is the caller's job.
"""
from dataclasses import dataclass
import re
from typing import Any, Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import Config, get_global_config
from core.error import ValidationError
from models.domain.chat import (
    AreaChairResponseSchema,
    AuthorResponseSchema,
    ChatFallbackRawResponseSchema,
    ChatModelName,
    ChatModelResponseSchema,
    MetaReviewResponseSchema,
    ChatReviewerRebuttal,
    ReviewerResponseSchema,
    ChatRevisedSection,
)


@dataclass
class ChatResponse:
    """One normalized chat invocation: the parsed payload, the token usage and
    any structured-output parsing error. ``raw`` keeps the provider message for
    debugging/traces — callers use the extracted token fields, not ``raw`` — so
    the LangChain type never leaks past this layer."""
    response_schema: ChatModelResponseSchema | None
    raw: AIMessage | None
    """None when no LLM call happened (e.g. token estimation)."""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    parsing_error: Exception | None = None


class Factory:
    """Builds the chat model (per provider) and the prompt / variables."""

    @staticmethod
    def create_chat(model: ChatModelName, temperature: float) -> "Chat":
        """Create a chat client for the given model name and temperature.
        The mock model has no provider client: it short-circuits to MockChat."""
        if ChatModelName(model).is_mock():
            return MockChat()
        chat_model = Factory._create_chat_model(model, temperature)
        return Chat(chat_model, model_name=model)

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
    def _create_chat_model(model: ChatModelName, temperature: float) -> BaseChatModel:
        """Create a chat model client for the given model name and temperature."""
        config = get_global_config()
        for predicate, build in Factory._client_builders():
            if predicate(model):
                return build(model, temperature, config)
        raise ValueError(f"Unsupported LLM model: {model}")

    @staticmethod
    def _client_builders() -> list[tuple[Callable[[ChatModelName], bool], Callable[..., BaseChatModel]]]:
        return [
            (ChatModelName.is_ollama, Factory._build_ollama),
            (ChatModelName.is_openai, Factory._build_openai),
            (ChatModelName.is_anthropic, Factory._build_anthropic),
            (ChatModelName.is_other_llm_provider, Factory._build_other_llm_provider),
        ]

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

    def __init__(self, chat_model: BaseChatModel, model_name: ChatModelName | None = None):
        self._chat_model = chat_model
        self._model_name = model_name

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
        raw fallback is returned. ``label`` names the caller in parse errors.
        The ``token-estimation`` pseudo-model short-circuits to a cost estimate
        without any LLM call."""
        
        if self._model_name == ChatModelName.MOCK:
            return MockChat().invoke(system_prompt, message, context, response_schema)
        
        chat_message = Factory.create_chat_message(system_prompt)
        chat_variables = Factory.create_chat_variables(message, context)
        if response_schema is None:
            return Invoke.invoke_without_response_schema(self._chat_model, chat_message, chat_variables)
        return Invoke.invoke_with_response_schema(self._chat_model, response_schema, label, chat_message, chat_variables)
 
    
class MockChat(Chat):
    """A mock chat facade for testing, returning canned responses."""

    def __init__(self):
        super().__init__(None, model_name=ChatModelName.MOCK)
        
    def invoke(
        self,
        system_prompt: str,
        message: str,
        context: str | None = None,
        response_schema: type[ChatModelResponseSchema] | None = None,
        label: str = "",
    ) -> ChatResponse:
        """Return the canned instance for the requested schema (so agents and
        graph run unchanged) with token usage *estimated* from the inputs; with
        no schema, the fallback response carries the estimate summary."""

        system_prompt_tokens = self._estimate_tokens(system_prompt)
        message_tokens = self._estimate_tokens(message)
        context_tokens = self._estimate_tokens(context) if context else 0
        response_schema_tokens = self._estimate_tokens(response_schema.__name__) + 10 if response_schema is not None else 0

        chat_schemas = _MOCK_INSTANCES.get(response_schema) if response_schema is not None else None

        estimated_input_tokens = system_prompt_tokens + message_tokens + context_tokens + response_schema_tokens
        estimated_output_tokens = self._estimate_tokens(str(chat_schemas)) if chat_schemas is not None else 20
        total_estimated_tokens = estimated_input_tokens + estimated_output_tokens

        if chat_schemas is None:
            chat_schemas = ChatFallbackRawResponseSchema(
                response=(
                    f"[mock] input≈{estimated_input_tokens}, "
                    f"output≈{estimated_output_tokens}, total≈{total_estimated_tokens}"
                )
            )

        return ChatResponse(
            response_schema=chat_schemas,
            raw=None,
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
            total_tokens=total_estimated_tokens,
            parsing_error=None,
        )
        
    def _estimate_tokens(self, message: str) -> int:
        if not message or not message.strip():
            return 0

        n_chars = len(message)
        n_words = len(message.split())
        n_punct = len(re.findall(r"[^\w\s]", message))

        by_chars = n_chars / 4
        by_words = n_words / 0.75

        return round((by_chars + by_words) / 2 + n_punct * 0.25)
 
    
_MOCK_INSTANCES: dict[type[ChatModelResponseSchema], ChatModelResponseSchema] = {
    ReviewerResponseSchema: ReviewerResponseSchema(
        summary="Solid approach, clear experiments, reasonable scope.",
        significance_and_novelty="Original contribution with respect to prior art.",
        reasons_for_acceptance=["Rigorous methodology", "Convincing results", "Clear presentation"],
        reasons_for_rejection=["Limited sensitivity analysis", "Weak baseline coverage"],
        suggestions=["Add ablation study", "Expand related work"],
        rating=6,
        confidence=4,
    ),
    MetaReviewResponseSchema: MetaReviewResponseSchema(
        summary="Solid foundations but revisions needed before acceptance.",
        key_points=["Methodology valid", "Presentation improvable", "Contribution interesting"],
        overall_score=6,
        recommendation="minor_revision",
    ),
    AreaChairResponseSchema: AreaChairResponseSchema(
        summary="Reviewer concerns are moderate and addressable; minor revision required.",
        justification="Contribution is valid; concerns can be addressed with limited rework.",
        decision="minor_revision",
        confidence=4,
    ),
    AuthorResponseSchema: AuthorResponseSchema(
        rebuttal="We thank the reviewers; revisions address all major concerns.",
        reviewer_rebuttals=[
            ChatReviewerRebuttal(reviewer_name=f"reviewer_{i}", response=f"Targeted response to reviewer {i}.")
            for i in (1, 2, 3)
        ],
        revised_sections=[
            ChatRevisedSection(section_name="methods", content="Expanded methods section with hyperparameters."),
            ChatRevisedSection(section_name="results", content="Added sensitivity analysis and extra baselines."),
        ],
        key_changes=["Sensitivity analysis", "Hyperparameter details", "Additional baselines"],
    ),
}