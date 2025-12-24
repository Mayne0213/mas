"""
LangGraph K8s Infrastructure Planning Workflow
워크플로우: Planning → Research → Prompt Generation → End
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from agents import (
    AgentState,
    orchestrator_node,
    planning_node,
    research_node,
    prompt_generator_node
)


def router(state: AgentState) -> Literal[
    "planning",
    "research",
    "prompt_generator",
    "end"
]:
    """
    다음 에이전트 라우팅 로직
    K8s 인프라 계획: planning → research → prompt_generator → end
    """
    current = state.get("current_agent", "orchestrator")

    # 명시적으로 지정된 다음 에이전트로 이동
    if current in ["planning", "research", "prompt_generator"]:
        return current

    # end 상태
    if current == "end":
        return "end"

    # 기본값: planning부터 시작
    return "planning"


def create_mas_workflow():
    """
    K8s Infrastructure Planning Workflow 생성

    워크플로우:
    User Request (e.g., "Deploy Tekton")
        ↓
    Orchestrator → Planning → Orchestrator
        ↓
    Research (K8s cluster analysis) → Orchestrator
        ↓
    Prompt Generator (Markdown implementation guide) → Orchestrator
        ↓
    End (User copies prompt to another AI)
    """
    workflow = StateGraph(AgentState)

    # 노드 추가
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("research", research_node)
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
            "prompt_generator": "prompt_generator",
            "end": END
        }
    )

    # 각 에이전트는 작업 후 Orchestrator로 복귀
    workflow.add_edge("planning", "orchestrator")
    workflow.add_edge("research", "orchestrator")
    workflow.add_edge("prompt_generator", "orchestrator")

    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_workflow()
