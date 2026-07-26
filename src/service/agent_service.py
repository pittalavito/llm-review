
from config import Config

from domain.chat.base import Factory as ChatFactory, Chat
from domain.chat.base import ChatModelName
from domain.agent.base import Agent, Factory as AgentFactory

class AgentService:
    
    def __init__(self, config: Config):
        self.config = config
        self.chat_clients_instances = {}
        self.agent_instances = {}

    def build_chat(
        self, 
        model: ChatModelName, 
        temperature: float
    ) -> Chat:
        """Create a new chat client for the given model and temperature."""
        key = (model, temperature)
        if key in self.chat_clients_instances:
            return self.chat_clients_instances[key]
        chat: Chat = ChatFactory.create_chat(self.config, model=model, temperature=temperature)
        self.chat_clients_instances[key] = chat
        return self.chat_clients_instances[key]
    
    def build_agent(
        self, 
        agent_role: str, 
        model: ChatModelName, 
        temperature: float, 
        agent_index: int | None = None, 
        system_prompt: str = ""
    ) -> Agent:    
        """Create a new agent for the given role and chat client."""
        key = (agent_role, model, temperature, agent_index, system_prompt)
        if key in self.agent_instances:
            return self.agent_instances[key]
        chat_client = self.build_chat(model=model, temperature=temperature)
        agent = AgentFactory.create_agent(agent_role=agent_role, chat=chat_client, agent_index=agent_index, system_prompt=system_prompt)
        self.agent_instances[key] = agent
        return agent
    
    