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

        if request.system_prompt_request is not None:
            promt_request = request.system_prompt_request
            system_prompt = self._prompt_service.build_system_prompt(
                agent_role=request.agent_role, 
                promt_label=promt_request.base_prompt_version,
                instruction_labels=promt_request.instruction_labels
            )
        else:
            system_prompt = None
            
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
