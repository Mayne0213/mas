"""
Prompt Generator Agent (Claude 4.5)
다른 AI에게 전달할 구현 프롬프트를 Markdown으로 생성
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json


# Claude 4.5 모델 초기화
claude_prompt_gen = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.5
)


PROMPT_GENERATOR_SYSTEM = """You are the Prompt Generator Agent.

## Role
Generate implementation prompts for other AI assistants (like Claude Code, ChatGPT, etc.).

## Input
- Planning data: folder structure, YAML files, K8s resources
- Research data: current cluster state, existing resources

## Output Format (Markdown)
Create a comprehensive prompt that another AI can use to implement the infrastructure:

```markdown
# Deploy [TOOL_NAME] to Kubernetes

## Context
[Brief description of current cluster state from research data]

## Folder Structure
Create the following directory structure:
```
deploy/[tool]/
├── base/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── kustomization.yaml
└── overlays/
    └── prod/
        └── kustomization.yaml
```

## Implementation Steps

### Step 1: [Title]
**File:** `deploy/[tool]/base/namespace.yaml`
```yaml
[Example YAML with placeholders]
```

### Step 2: [Title]
**File:** `deploy/[tool]/base/deployment.yaml`
```yaml
[Example YAML with specific recommendations]
```

## Key Considerations
- Resource limits: [specific recommendations based on cluster]
- Storage: [based on available StorageClasses]
- Networking: [based on existing services]
- RBAC: [specific permissions needed]

## Validation Commands
```bash
kubectl apply -k deploy/[tool]/overlays/prod
kubectl get pods -n [namespace]
kubectl logs -n [namespace] deployment/[name]
```

## Expected Outcome
[What should be running after implementation]
```

## Guidelines
1. Be specific and actionable
2. Include actual YAML examples (not just descriptions)
3. Reference the cluster's current state from research data
4. Provide validation steps
5. Make it copy-paste ready for another AI
"""


def prompt_generator_node(state: AgentState) -> AgentState:
    """
    Prompt Generator 노드: 다른 AI에게 전달할 구현 프롬프트 생성
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_data = state.get("research_data", {})

    # 입력 데이터 준비
    plan_summary = json.dumps(task_plan, indent=2, ensure_ascii=False) if task_plan else "No plan available"
    research_summary = json.dumps(research_data, indent=2, ensure_ascii=False) if research_data else "No research data"

    # 사용자 원래 요청
    user_request = messages[0]["content"] if messages else "Deploy infrastructure"

    print(f"\n{'='*80}")
    print(f"Prompt Generator Agent - Generating implementation prompt")
    print(f"{'='*80}")

    # Claude 호출
    response = claude_prompt_gen.invoke([
        SystemMessage(content=PROMPT_GENERATOR_SYSTEM),
        HumanMessage(content=f"""Generate an implementation prompt for this request:

**User Request:** {user_request}

**Planning Data:**
```json
{plan_summary}
```

**Research Data (Cluster State):**
```json
{research_summary}
```

Create a comprehensive Markdown prompt that another AI can use to implement this infrastructure.
Include specific YAML examples, folder structure, and validation steps.
""")
    ])

    content = response.content

    print(f"✅ Prompt generated ({len(content)} characters)")

    # 상태 업데이트
    state["implementation_prompt"] = content
    state["messages"].append({
        "role": "prompt_generator",
        "content": content
    })
    state["current_agent"] = "end"  # 완료

    return state
