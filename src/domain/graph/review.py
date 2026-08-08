from __future__ import annotations

import json
from enum import StrEnum

from langgraph.graph import END, START, StateGraph

from domain.agent.base import Agent
from domain.graph.base import Graph, AgentNode
from domain.graph.state import ReviewState

from models.domain.agent import AgentRole
from models.domain.chat import AreaChairResponseSchema, ChatReviewDecision, MetaReviewResponseSchema, ReviewerResponseSchema, AuthorResponseSchema
from models.domain.graph import CreateGraphReviewRequest
from models.domain.run_record import AgentResponseRecord


class NodeNames(StrEnum):
    REVIEWER = "Reviewer"
    META_REVIEWER = "MetaReviewer"
    AREA_CHAIR = "AreaChair"
    AUTHOR_AGENT = "AuthorAgent"


class ReviewerNode(AgentNode):

    def set_message(self, state: ReviewState) -> str:
        revised = state.get("revised_sections")
        if not revised:
            return "Review the paper provided in your context and produce your structured assessment."

        rebuttal = (state.get("author_response") or {}).get("rebuttal") or "(none)"
        sections = "\n\n".join(f"## {name}\n{content}" for name, content in revised.items())
        return (
            "Re-review the paper. The authors submitted a rebuttal and revised sections — "
            "update your assessment, stating whether your concerns were addressed.\n\n"
            f"Author rebuttal:\n{rebuttal}\n\n"
            f"Revised sections:\n{sections}"
        )

    def update_state(self, state: ReviewState, schema: ReviewerResponseSchema | None, record: AgentResponseRecord) -> dict:
        if schema is None:
            return {
                "reviews_response": state.get("reviews_response") or [],
                "agent_records": [record.model_dump()]
            }
        else:
            return {
                "reviews_response": [schema.model_dump()],
                "agent_records": [record.model_dump()]
            }


class MetaReviewerNode(AgentNode):

    def set_message(self, state: ReviewState) -> str:
        reviews = state.get("reviews_response") or []
        joined = "\n\n".join(f"- {json.dumps(review)}" for review in reviews) if reviews else "(no reviews)"
        return f"Synthesize the following {len(reviews)} reviews into a meta-review:\n\n{joined}"

    def update_state(self, state: ReviewState, schema: MetaReviewResponseSchema | None, record: AgentResponseRecord) -> dict:
        if schema is None:
            return {
                "meta_review_response": None,
                "current_round": state["current_round"] + 1,
                "agent_records": [record.model_dump()],
            }
        else:
            return {
                "meta_review_response": schema.model_dump(),
                "current_round": state["current_round"] + 1,
                "agent_records": [record.model_dump()],
            }


class AreaChairNode(AgentNode):
    round_offset = -1

    def set_message(self, state: ReviewState) -> str:
        return f"Make the final decision based on the meta-review:\n\n{state.get('meta_review_response')}"

    def update_state(self, state: ReviewState, schema: AreaChairResponseSchema | None, record: AgentResponseRecord) -> dict:
        if schema is None:
            return {
                "area_chair_response": None,
                "decision": None,
                "agent_records": [record.model_dump()],
            }
        else:
            return {
                "area_chair_response": schema.model_dump(),
                "decision": schema.decision,
                "agent_records": [record.model_dump()],
            }


class AuthorNode(AgentNode):

    round_offset = -1

    def set_message(self, state: ReviewState) -> str:
        reviews = state.get("reviews_response") or []
        return (
            f"Write a rebuttal and revisions addressing the decision "
            f"({state.get('area_chair_response')}) and {len(reviews)} reviews."
        )

    def update_state(self, state: ReviewState, schema: AuthorResponseSchema | None, record: AgentResponseRecord) -> dict:
        if schema is None:
            return {
                "author_response": None,
                "revised_sections": None,
                "agent_records": [record.model_dump()],
            }
        else:
            payload = schema
            return {
                "author_response": payload.model_dump(),
                "revised_sections": {s.section_name: s.content for s in payload.revised_sections},
                "agent_records": [record.model_dump()],
            }


class GraphReview(Graph):

    state_schema = ReviewState

    def build_initial_state(self, request: CreateGraphReviewRequest) -> ReviewState:
        return {
            "paper_id": request.paper_id,
            "reviews_response": [],
            "meta_review_response": None,
            "area_chair_response": None,
            "decision": None,
            "author_response": None,
            "revised_sections": None,
            "current_round": 0,
            "max_rounds": request.graph_config.max_rounds,
            "agent_records": [],
        }

    def _register_nodes(self, graph: StateGraph, agents: dict[str, Agent]) -> None:
        reviewer_agents = self._get_reviewers()
        if not reviewer_agents:
            raise ValueError("The graph needs at least one reviewer agent.")

        graph.add_node(NodeNames.REVIEWER, lambda state: {})
        for reviewer in reviewer_agents:
            graph.add_node(reviewer.name, ReviewerNode(reviewer))

        graph.add_node(NodeNames.META_REVIEWER, MetaReviewerNode(agents[AgentRole.META_REVIEWER.value]))
        graph.add_node(NodeNames.AREA_CHAIR, AreaChairNode(agents[AgentRole.AREA_CHAIR.value]))
        graph.add_node(NodeNames.AUTHOR_AGENT, AuthorNode(agents[AgentRole.AUTHOR_AGENT.value]))

    def _register_edges(self, graph: StateGraph) -> None:
        graph.add_edge(START, NodeNames.REVIEWER)

        for reviewer in self._get_reviewers():
            graph.add_edge(NodeNames.REVIEWER, reviewer.name)
            graph.add_edge(reviewer.name, NodeNames.META_REVIEWER)

        graph.add_edge(NodeNames.META_REVIEWER, NodeNames.AREA_CHAIR)

    def _register_conditional_edges(self, graph: StateGraph) -> None:
        area_chair_dict: dict = {
            "accept": END, 
            "fail": END,
            "revise": NodeNames.AUTHOR_AGENT
        }
        author_dict: dict = {
            "loop": NodeNames.REVIEWER, 
            "end": END,
            "fail": END
        }
        graph.add_conditional_edges(NodeNames.AREA_CHAIR, self._route_after_area_chair, area_chair_dict)
        graph.add_conditional_edges(NodeNames.AUTHOR_AGENT, self._route_after_author, author_dict)
        
    def _route_after_area_chair(self, state: ReviewState) -> str:
        """After the Area Chair: terminate only on accept; a missing decision
        means the Area Chair failed to produce structured output, so fail
        instead of looping forever."""
        if state.get("decision") is None:
            return "fail"
        if state.get("decision") == ChatReviewDecision.ACCEPT:
            return "accept"
        return "revise"    

    def _route_after_author(self, state: ReviewState) -> str:
        """After the Author: keep looping while rounds remain, else end."""
        if state.get("author_response") is None:
            return "fail"
        if state["current_round"] >= state["max_rounds"]:
            return "end"
        return "loop"
    
    def _get_reviewers(self) -> list[Agent]:
        return sorted(
            (a for a in self.agents.values() if a.agent_role is AgentRole.REVIEWER),
            key=lambda a: a.agent_index or 0,
        )

