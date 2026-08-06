from domain.agent.base import Agent, Factory as AgentFactory

from models.domain.agent import CreateAgentRequest
from models.domain.graph import CreateGraphReviewRequest

from service.chat_service import ChatService
from service.prompt_service import PromptService
from service.retrieval_service import RetrievalService

class AgentService:

    def __init__(self, chat_service: ChatService, prompt_service: PromptService, retrieval_service: RetrievalService):
        self._chat_service = chat_service
        self._prompt_service = prompt_service
        self._retrieval_service = retrieval_service

    def build_agent(self, request: CreateAgentRequest) -> Agent:
        """Create a new agent for the given role and chat client."""
        chat = self._chat_service.build_chat(model=request.model, temperature=request.temperature)
        system_prompt = self._prompt_service.build_system_prompt_from_preset_id(agent_role=request.agent_role, preset_id=request.prompt_preset_id)
    
        if system_prompt is None:
            raise ValueError(f"No system prompt could be built for agent role '{request.agent_role}' and preset id '{request.prompt_preset_id}'.")        
            
        agent = AgentFactory.create_agent(request=request, chat=chat, system_prompt=system_prompt)

        context = self._retrieval_service.get_agent_context(request)
        if context is not None:
            agent.set_context(context)
        return agent

    def build_agents_for_graph(self, request: CreateGraphReviewRequest) -> dict[str, Agent]:
        agents: dict[str, Agent] = {}
        for req in AgentFactory.create_agent_requests(request):
            agent = self.build_agent(req)
            agents[agent.name] = agent
        return agents
