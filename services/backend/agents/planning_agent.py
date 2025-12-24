"""
Planning Agent (Claude 4.5)
작업 계획 수립 및 단계별 태스크 정의
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json


# Claude 4.5 모델 초기화
claude_planning = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.3  # 계획은 더 deterministic하게
)


PLANNING_PROMPT = """You are the Planning Agent in a Multi-Agent System.

## Role
Analyze user requests and create actionable task plans.

## Process
1. Understand what the user wants
2. Classify: backend / frontend / infrastructure / mixed
3. Break down into steps
4. Identify information needed
5. Define success criteria

## Output Format (JSON)
```json
{
  "task_type": "backend | frontend | infrastructure | mixed",
  "summary": "Brief task summary",
  "steps": [
    {"step": 1, "description": "...", "agent": "research|code_*"}
  ],
  "research_needed": ["What info to gather"],
  "success_criteria": ["How to verify completion"]
}
```

Keep plans simple and actionable. Research agent can explore and find things automatically.
"""


def planning_node(state: AgentState) -> AgentState:
    """
    Planning 노드: 작업 계획 수립
    """
    messages = state["messages"]
    user_request = messages[0]["content"] if messages else ""

    # Claude 호출
    response = claude_planning.invoke([
        SystemMessage(content=PLANNING_PROMPT),
        HumanMessage(content=f"사용자 요청: {user_request}")
    ])

    content = response.content

    # JSON 파싱 시도
    try:
        # JSON 블록 추출
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content

        task_plan = json.loads(json_str)
    except Exception as e:
        task_plan = {
            "task_type": "mixed",
            "summary": "계획 파싱 실패, Research Agent로 이동",
            "steps": [{"step": 1, "description": "정보 수집", "agent": "research"}],
            "research_needed": ["사용자 요청 관련 정보"],
            "success_criteria": ["작업 완료"],
            "error": str(e)
        }

    # 상태 업데이트
    state["task_plan"] = task_plan
    state["messages"].append({
        "role": "planning",
        "content": content
    })
    state["current_agent"] = "orchestrator"  # 다시 orchestrator로 반환

    return state
