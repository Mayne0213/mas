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


PLANNING_PROMPT = """You are the K8s Infrastructure Planning Agent.

## Role
Analyze user requests for Kubernetes infrastructure and create implementation plans.

## Your Mission
When a user wants to deploy something (e.g., "Tekton", "Harbor", "Prometheus"):
1. Understand what they want to deploy
2. Design high-level folder structure
3. Identify what K8s resources would be needed
4. Determine what cluster information to gather

## Output Format (JSON)
```json
{
  "task_type": "k8s_infrastructure",
  "summary": "Deploy X to Kubernetes cluster",
  "target_tool": "Name of the tool/service to deploy",
  "folder_structure": {
    "base_path": "deploy/X",
    "directories": ["base", "overlays/prod"]
  },
  "k8s_resources": [
    {"type": "Namespace", "name": "X"},
    {"type": "Deployment", "name": "X"},
    {"type": "Service", "name": "X-svc"}
  ],
  "research_needed": [
    "Check Kubernetes version",
    "Check existing similar tools",
    "Verify available resources",
    "Check storage classes"
  ],
  "requirements": {
    "min_k8s_version": "1.24",
    "estimated_resources": {"cpu": "2", "memory": "4Gi"},
    "dependencies": ["tool1", "tool2"]
  }
}
```

Keep it simple and high-level. Focus on what needs to be checked, not detailed YAML structures.
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

        # 사용자 친화적인 한국어 요약 생성
        summary_parts = []

        target_tool = task_plan.get("target_tool", "알 수 없음")
        summary_parts.append(f"📋 **{target_tool}** 요구사항 분석 완료\n")

        # 필요 조건
        requirements = task_plan.get("requirements", {})
        if requirements:
            summary_parts.append("**필요 조건**")
            if requirements.get("min_k8s_version"):
                summary_parts.append(f"- Kubernetes 버전: 최소 {requirements['min_k8s_version']} 이상")

            resources = requirements.get("estimated_resources", {})
            if resources:
                cpu = resources.get("cpu", "")
                memory = resources.get("memory", "")
                storage = resources.get("storage", "")
                resource_str = []
                if cpu:
                    resource_str.append(f"CPU {cpu}코어")
                if memory:
                    resource_str.append(f"메모리 {memory}")
                if storage:
                    resource_str.append(f"스토리지 {storage}")
                if resource_str:
                    summary_parts.append(f"- 예상 리소스: {', '.join(resource_str)}")

            dependencies = requirements.get("dependencies", [])
            if dependencies:
                deps_str = ", ".join(dependencies)
                summary_parts.append(f"- 의존성: {deps_str}")

        # 확인이 필요한 사항
        research_needed = task_plan.get("research_needed", [])
        if research_needed:
            summary_parts.append("\n**확인이 필요한 사항**")
            for item in research_needed[:5]:  # 최대 5개
                # 영어를 한국어로 간단히 변환
                item_ko = item.replace("Check", "확인:").replace("Verify", "검증:").replace("Analyze", "분석:")
                summary_parts.append(f"- {item_ko}")

        user_friendly_content = "\n".join(summary_parts)

    except Exception as e:
        task_plan = {
            "task_type": "mixed",
            "summary": "계획 파싱 실패",
            "research_needed": ["클러스터 상태 확인"],
            "error": str(e)
        }
        user_friendly_content = "📋 요구사항 분석 중...\n\n기본 정보를 확인하겠습니다."

    # 상태 업데이트
    state["task_plan"] = task_plan
    state["messages"].append({
        "role": "planning",
        "content": user_friendly_content
    })
    state["current_agent"] = "orchestrator"  # 다시 orchestrator로 반환

    return state
