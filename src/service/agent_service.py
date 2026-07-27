from domain.chat.base import Chat, Factory as ChatFactory
from domain.agent.base import Agent, Factory as AgentFactory

from domain.models.chat import ChatModelName
from domain.models.agent import CreateAgentRequest
from domain.models.prompt import PromptVersion

from service.store_service import StoreService
from service.retrieval_service import RetrievalService

class AgentService:
    
    def __init__(self, retrieval_service: RetrievalService):
        self.retrieval_service = retrieval_service
        self.store_service = retrieval_service.store_service
        self.config = retrieval_service.config
        self.chat_clients_instances = {}
    
    def build_agent(self, request: CreateAgentRequest) -> Agent:
        """Create a new agent for the given role and chat client."""
        chat = self._build_chat(model=request.model, temperature=request.temperature)
        system_prompt = self._build_system_prompt(agent_role=request.agent_role, version_label=request.prompt_version)
        context = self._build_content(request)
        agent = AgentFactory.create_agent(request=request, chat=chat, system_prompt=system_prompt)
        agent.set_context(context)
        return agent
    
    def _build_chat(self, model: ChatModelName, temperature: float) -> Chat:
        """Create a new chat client for the given model and temperature."""
        key = (model, temperature)
        if key in self.chat_clients_instances:
            return self.chat_clients_instances[key]
        chat: Chat = ChatFactory.create_chat(self.config, model=model, temperature=temperature)
        self.chat_clients_instances[key] = chat
        return self.chat_clients_instances[key]
    
    def _build_system_prompt(self, agent_role: str, version_label: str) -> str:
        """Retrieve the system prompt for the given agent role and version label."""
        prompt_version: PromptVersion = self.store_service.get_by_role_label(agent_role=agent_role, version_label=version_label)
        if prompt_version is None or prompt_version.template is None:
            raise ValueError(f"No prompt found for role '{agent_role}' and version '{version_label}'.")
        return prompt_version.template
    
    def _build_content(self, request):
        return self.retrieval_service.get_agent_context(request)