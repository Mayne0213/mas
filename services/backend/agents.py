"""
MAS (Multi-Agent System) 에이전트 정의
"""
from typing import Annotated, Literal, TypedDict
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage
import os


class AgentState(TypedDict):
    """에이전트 간 공유되는 상태"""
    messages: list
    current_agent: str
    task_type: str
    result: dict


# ===== 1. Claude Code - Orchestrator =====
claude_orchestrator = ChatAnthropic(
    model="claude-3-5-sonnet-latest",  # Always use latest version
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
)

ORCHESTRATOR_PROMPT = """당신은 MAS의 총괄 조율자이자 DevOps 전문가입니다.

**역할**:
- 사용자 요청을 분석하여 적절한 에이전트에게 작업 할당
- Kubernetes, ArgoCD, Helm, Kustomize 관리
- CI/CD 파이프라인 구성
- 최종 코드 리뷰 및 승인

**사용 가능한 에이전트**:
1. backend_developer: FastAPI, Node.js 백엔드 개발
2. frontend_developer: Next.js, React 프론트엔드 개발
3. sre_specialist: 모니터링, 성능 최적화, 보안

요청을 분석하고 어떤 에이전트가 처리해야 할지 결정하세요.
"""


# ===== 2. Groq #1 - Backend Developer =====
# Groq OpenAI-compatible endpoint
GROQ_API_BASE = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

groq_backend = ChatOpenAI(
    model=os.getenv("GROQ_BACKEND_MODEL", "llama-3.3-70b-specdec"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.7,
)

BACKEND_PROMPT = """당신은 백엔드 개발 전문가입니다.

**역할**:
- FastAPI, Node.js 백엔드 개발
- REST API 설계 및 구현
- 데이터베이스 쿼리 최적화
- 비즈니스 로직 구현

요청된 백엔드 작업을 수행하고 코드를 생성하세요.
"""


# ===== 3. Groq #2 - Frontend Developer =====
groq_frontend = ChatOpenAI(
    model=os.getenv("GROQ_FRONTEND_MODEL", "llama-3.1-8b-instant"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.7,
)

FRONTEND_PROMPT = """당신은 프론트엔드 개발 전문가입니다.

**역할**:
- Next.js, React 컴포넌트 개발
- UI/UX 구현
- 상태 관리
- 반응형 디자인

요청된 프론트엔드 작업을 수행하고 코드를 생성하세요.
"""


# ===== 4. Groq #3 - SRE Specialist =====
groq_sre = ChatOpenAI(
    model=os.getenv("GROQ_SRE_MODEL", "llama-3.1-8b-instant"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.3,
)

SRE_PROMPT = """당신은 SRE(Site Reliability Engineer) 전문가입니다.

**역할**:
- 시스템 모니터링 (Prometheus, Grafana, Loki)
- 로그 분석 및 알람 설정
- 성능 튜닝
- 보안 취약점 점검

요청된 SRE 작업을 수행하고 솔루션을 제시하세요.
"""


def orchestrator_node(state: AgentState) -> AgentState:
    """Claude Code - 작업 분석 및 할당"""
    messages = state["messages"]
    
    response = claude_orchestrator.invoke([
        SystemMessage(content=ORCHESTRATOR_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    # 작업 타입 결정
    content = response.content.lower()
    if "backend" in content or "api" in content or "fastapi" in content:
        next_agent = "backend_developer"
    elif "frontend" in content or "ui" in content or "react" in content:
        next_agent = "frontend_developer"
    elif "monitoring" in content or "performance" in content or "sre" in content:
        next_agent = "sre_specialist"
    else:
        next_agent = "orchestrator"  # 자신이 직접 처리
    
    state["messages"].append({
        "role": "orchestrator",
        "content": response.content
    })
    state["current_agent"] = next_agent
    
    return state


def backend_node(state: AgentState) -> AgentState:
    """Groq #1 - 백엔드 개발"""
    messages = state["messages"]
    
    response = groq_backend.invoke([
        SystemMessage(content=BACKEND_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    state["messages"].append({
        "role": "backend_developer",
        "content": response.content
    })
    state["current_agent"] = "orchestrator"  # 결과를 오케스트레이터에게 반환
    
    return state


def frontend_node(state: AgentState) -> AgentState:
    """Groq #2 - 프론트엔드 개발"""
    messages = state["messages"]
    
    response = groq_frontend.invoke([
        SystemMessage(content=FRONTEND_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    state["messages"].append({
        "role": "frontend_developer",
        "content": response.content
    })
    state["current_agent"] = "orchestrator"
    
    return state


def sre_node(state: AgentState) -> AgentState:
    """Groq #3 - SRE 작업"""
    messages = state["messages"]
    
    response = groq_sre.invoke([
        SystemMessage(content=SRE_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    state["messages"].append({
        "role": "sre_specialist",
        "content": response.content
    })
    state["current_agent"] = "orchestrator"
    
    return state


def router(state: AgentState) -> Literal["backend_developer", "frontend_developer", "sre_specialist", "end"]:
    """다음 에이전트 라우팅"""
    current = state.get("current_agent", "orchestrator")
    
    if current == "backend_developer":
        return "backend_developer"
    elif current == "frontend_developer":
        return "frontend_developer"
    elif current == "sre_specialist":
        return "sre_specialist"
    else:
        return "end"


# ===== LangGraph 워크플로우 구성 =====
def create_mas_graph():
    """MAS 워크플로우 그래프 생성"""
    workflow = StateGraph(AgentState)
    
    # 노드 추가
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("backend_developer", backend_node)
    workflow.add_node("frontend_developer", frontend_node)
    workflow.add_node("sre_specialist", sre_node)
    
    # 엣지 정의
    workflow.set_entry_point("orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        router,
        {
            "backend_developer": "backend_developer",
            "frontend_developer": "frontend_developer",
            "sre_specialist": "sre_specialist",
            "end": END
        }
    )
    
    # 각 에이전트는 작업 후 orchestrator로 복귀
    workflow.add_edge("backend_developer", "orchestrator")
    workflow.add_edge("frontend_developer", "orchestrator")
    workflow.add_edge("sre_specialist", "orchestrator")
    
    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_graph()

