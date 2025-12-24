"""
LangGraph Iterative Workflow
반복적 워크플로우: Planning → Research → Code → Review (최대 3회 반복)
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from agents import (
    AgentState,
    orchestrator_node,
    planning_node,
    research_node,
    backend_code_node,
    frontend_code_node,
    infrastructure_code_node,
    review_node
)


def router(state: AgentState) -> Literal[
    "planning",
    "research",
    "code_backend",
    "code_frontend",
    "code_infrastructure",
    "review",
    "end"
]:
    """
    다음 에이전트 라우팅 로직
    """
    current = state.get("current_agent", "orchestrator")

    # 명시적으로 지정된 다음 에이전트로 이동
    if current in [
        "planning",
        "research",
        "code_backend",
        "code_frontend",
        "code_infrastructure",
        "review"
    ]:
        return current

    # end 상태
    if current == "end":
        return "end"

    # 기본값: planning부터 시작
    return "planning"


def create_mas_workflow():
    """
    MAS Iterative Workflow 생성

    워크플로우:
    User Request
        ↓
    Orchestrator → Planning → Orchestrator
        ↓
    Research → Orchestrator
        ↓
    Code (Backend/Frontend/Infrastructure) → Orchestrator
        ↓
    Review → Orchestrator
        ↓ (if not approved and iteration < 3)
    Research (반복)
        ↓ (if approved or iteration >= 3)
    End
    """
    workflow = StateGraph(AgentState)

    # 노드 추가
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("research", research_node)
    workflow.add_node("code_backend", backend_code_node)
    workflow.add_node("code_frontend", frontend_code_node)
    workflow.add_node("code_infrastructure", infrastructure_code_node)
    workflow.add_node("review", review_node)

    # 시작점: Orchestrator
    workflow.set_entry_point("orchestrator")

    # Orchestrator의 조건부 라우팅
    workflow.add_conditional_edges(
        "orchestrator",
        router,
        {
            "planning": "planning",
            "research": "research",
            "code_backend": "code_backend",
            "code_frontend": "code_frontend",
            "code_infrastructure": "code_infrastructure",
            "review": "review",
            "end": END
        }
    )

    # 각 에이전트는 작업 후 Orchestrator로 복귀
    workflow.add_edge("planning", "orchestrator")
    workflow.add_edge("research", "orchestrator")
    workflow.add_edge("code_backend", "orchestrator")
    workflow.add_edge("code_frontend", "orchestrator")
    workflow.add_edge("code_infrastructure", "orchestrator")

    # Review는 승인 여부에 따라 처리 (review_node 내부에서 current_agent 설정)
    workflow.add_edge("review", "orchestrator")

    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_workflow()
