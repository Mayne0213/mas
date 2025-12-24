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
Analyze user requests for Kubernetes infrastructure and create detailed implementation plans.

## Your Mission
When a user wants to deploy something (e.g., "Tekton", "Harbor", "Prometheus"):
1. Understand what they want to deploy
2. Design the folder structure for K8s manifests
3. Plan YAML file organization
4. Identify what K8s resources are needed
5. Determine what information to gather from their cluster

## Output Format (JSON)
```json
{
  "task_type": "k8s_infrastructure",
  "summary": "Deploy X to Kubernetes cluster",
  "target_tool": "Name of the tool/service to deploy",
  "folder_structure": {
    "base_path": "deploy/X",
    "directories": ["base", "overlays/prod", "overlays/dev"],
    "files": {
      "base/deployment.yaml": "Main deployment manifest",
      "base/service.yaml": "Service definition",
      "base/kustomization.yaml": "Kustomize base"
    }
  },
  "k8s_resources": [
    {"type": "Namespace", "name": "X"},
    {"type": "Deployment", "name": "X"},
    {"type": "Service", "name": "X-svc"}
  ],
  "research_needed": [
    "Check existing namespaces",
    "Verify storage classes available",
    "Check current resource quotas"
  ],
  "implementation_steps": [
    {"step": 1, "description": "Create namespace and RBAC", "files": ["namespace.yaml", "serviceaccount.yaml"]},
    {"step": 2, "description": "Deploy core components", "files": ["deployment.yaml", "service.yaml"]}
  ]
}
```

Focus on K8s best practices: namespaces, RBAC, resource limits, health checks, and GitOps compatibility.
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
