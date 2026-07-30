import operator
from typing import Annotated
from domain.graph.base import BaseGraphState

class ReviewState(BaseGraphState):
    
    paper_id: str | None
    """ Paper identifier — enables per-agent RAG """

    retrieval_metadata: dict | None
    """ Metadata used for retrieval of relevant context for the paper """

    reviews: Annotated[list, operator.add]
    """ Reviews produced by the reviewers (committee size decided per run) — accumulated across all rounds """

    meta_review: dict | None
    """ Meta-review produced by the meta-reviewer agent """

    area_chair_response: dict | None
    """ Area chair response produced by the area chair agent """
    
    decision: str | None
    """ Current decision for the paper: accept | minor_revision | major_revision | reject (set by area chair) """
    
    author_response: dict | None
    """ Author rebuttal produced by the author agent """

    revised_sections: dict | None
    """ Revised paper sections extracted from author_response for easy injection into reviewers """

    current_round: int
    """ Current round of review (starts at 1) """
    
    max_rounds: int
    """ Maximum number of revision rounds before forcing termination """

    agent_runs: Annotated[list, operator.add]
    """ History of agent invocations — accumulated across all rounds """

    