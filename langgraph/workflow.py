"""
LangGraph K8s Infrastructure Planning Workflow
워크플로우: Planning → Research → Decision → Prompt Generation → End
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from agents import (
    AgentState,
    orchestrator_node,
    planning_node,
    research_node,
    decision_node,
    prompt_generator_node
)


def router(state: AgentState) -> Literal[
    "planning",
    "research",
    "decision",
    "prompt_generator",
    "end"
]:
    """
    다음 에이전트 라우팅 로직
    정보 조회: research → end
    도입 결정: planning → research → decision → prompt_generator (추천시) → end
    """
    current = state.get("current_agent", "orchestrator")

    # 명시적으로 지정된 다음 에이전트로 이동
    if current in ["planning", "research", "decision", "prompt_generator"]:
        return current

    # end 상태
    if current == "end":
        return "end"

    # 기본값: orchestrator가 결정
    return "planning"


def create_mas_workflow():
    """
    K8s Infrastructure Analysis & Decision Workflow 생성

    워크플로우 1 (정보 조회):
    User Request (e.g., "PostgreSQL 비밀번호 알려줘")
        ↓
    Orchestrator → Research → Orchestrator → End

    워크플로우 2 (도입 결정):
    User Request (e.g., "Tekton 도입할까?")
        ↓
    Orchestrator → Planning → Orchestrator
        ↓
    Research (K8s cluster analysis) → Orchestrator
        ↓
    Decision (추천/비추천) → Orchestrator
        ↓
    Prompt Generator (추천시만, 구현 가이드) → Orchestrator
        ↓
    End
    """
    workflow = StateGraph(AgentState)

    # 노드 추가
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("research", research_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("prompt_generator", prompt_generator_node)

    # 시작점: Orchestrator
    workflow.set_entry_point("orchestrator")

    # Orchestrator의 조건부 라우팅
    workflow.add_conditional_edges(
        "orchestrator",
        router,
        {
            "planning": "planning",
            "research": "research",
            "decision": "decision",
            "prompt_generator": "prompt_generator",
            "end": END
        }
    )

    # 각 에이전트는 작업 후 Orchestrator로 복귀
    workflow.add_edge("planning", "orchestrator")
    workflow.add_edge("research", "orchestrator")
    workflow.add_edge("decision", "orchestrator")
    workflow.add_edge("prompt_generator", "orchestrator")

    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_workflow()
