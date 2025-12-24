"""
Prompt Generator Agent (Claude 4.5)
Decision Agent의 추천 결과를 바탕으로 다른 AI에게 전달할 구현 프롬프트 생성
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
    temperature=0.3
)


PROMPT_GEN_SYSTEM = """You are the Implementation Prompt Generator.

## Role
Generate structured deployment prompts for other AI assistants based on existing project patterns.

## Environment Context
- **Projects Root**: `/home/ubuntu/Projects/`
- **Git Sync**: Local ↔️ Server auto-sync
- **ArgoCD**: All apps managed by ArgoCD
- **Vault**: Secrets managed by Vault ExternalSecrets
- **Kustomize**: All resources use Kustomization

## Project Structure Categories

### 1. Applications (`/home/ubuntu/Projects/applications/`)
**용도**: User-facing applications, development tools
**예시**: gitea, code-server, kubernetes-dashboard, homer, umami
**패턴**:
```
applications/{app-name}/
├── argocd/{app-name}.yaml       # ArgoCD Application
├── helm-values/{app-name}.yaml  # (Optional) Helm values
├── vault/*.yaml                 # (Optional) ExternalSecrets
└── kustomization.yaml           # Resource list
```

### 2. Cluster Infrastructure (`/home/ubuntu/Projects/cluster-infrastructure/`)
**용도**: Cluster-level infrastructure tools
**예시**: cert-manager, ingress-nginx, vault, external-secrets, reloader
**패턴**: Same as applications

### 3. Monitoring (`/home/ubuntu/Projects/monitoring/`)
**용도**: Monitoring and observability tools
**예시**: prometheus, grafana, loki

### 4. Databases (`/home/ubuntu/Projects/databases/`)
**용도**: Database services
**예시**: postgresql, redis, mongodb

### 5. Individual Projects (`/home/ubuntu/Projects/{project-name}/`)
**용도**: Standalone application projects
**예시**: mas, jaejadle, joossam, portfolio
**패턴**:
```
{project-name}/
├── deploy/
│   ├── argocd/{project-name}.yaml
│   └── k8s/
│       ├── base/
│       └── overlays/prod/
└── services/
```

## Output Format (Markdown)
Create a CONCISE guide (MAX 25 lines total):

```markdown
# [도구명] 배포 가이드

## 📍 배치
`/home/ubuntu/Projects/[category]/[tool-name]/`
**이유**: [1줄 설명]
**참고**: [category]/[example]/ 구조 동일

## 📂 구조
\`\`\`
[category]/[tool-name]/
├── argocd/[tool-name].yaml
├── kustomization.yaml
└── vault/*.yaml (선택)
\`\`\`

## 📋 파일
- **argocd/**: ArgoCD Application (repoURL, path, namespace)
- **kustomization.yaml**: 리소스 목록
- **vault/**: ExternalSecret (평문 금지)

## ✅ 필수
- ArgoCD 통합
- `/home/ubuntu/Projects/[category]/kustomization.yaml` 업데이트
```

CRITICAL: Response MUST be under 25 lines!

## Guidelines
1. **폴더 구조와 파일 역할**만 명시 (세부 YAML은 AI가 생성)
2. **카테고리 선택 기준** 명확히 제시
3. **기존 프로젝트 패턴** 반드시 준수
4. **ArgoCD, Vault, Kustomize 통합** 필수
5. **참고 예시** 제공하여 AI가 따라할 수 있도록
"""


def prompt_generator_node(state: AgentState) -> AgentState:
    """
    Prompt Generator 노드: 다른 AI에게 전달할 구현 프롬프트 생성
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_data = state.get("research_data", {})
    decision_report = state.get("decision_report", {})

    # 입력 데이터 준비
    plan_summary = json.dumps(task_plan, indent=2, ensure_ascii=False) if task_plan else "No plan"
    research_summary = json.dumps(research_data, indent=2, ensure_ascii=False) if research_data else "No research"

    # 사용자 원래 요청
    user_request = messages[0]["content"] if messages else "Deploy infrastructure"
    tool_name = task_plan.get("target_tool", "Unknown") if task_plan else "Unknown"

    print(f"\n{'='*80}")
    print(f"Prompt Generator - Creating implementation guide")
    print(f"{'='*80}")

    # Claude 호출
    response = claude_prompt_gen.invoke([
        SystemMessage(content=PROMPT_GEN_SYSTEM),
        HumanMessage(content=f"""다른 AI에게 전달할 구현 가이드를 생성해주세요:

**사용자 요청:** {user_request}
**배포 대상:** {tool_name}

**계획 데이터:**
```json
{plan_summary}
```

**클러스터 상태:**
```json
{research_summary}
```

위 정보를 바탕으로:
1. **적절한 카테고리 선택** (applications, cluster-infrastructure, monitoring, databases)
2. **폴더 구조만 제시** (세부 YAML은 다른 AI가 생성)
3. **파일별 역할 설명** (필수 필드와 용도만 명시)
4. **기존 패턴 준수** (ArgoCD, Vault, Kustomize 통합)
5. **참고 예시 제공** (동일 카테고리 프로젝트)

**중요**:
- 구조와 역할만 설명하고, 세부 YAML 내용은 생성하지 마세요
- 다른 AI가 이 가이드를 보고 YAML을 직접 생성할 수 있도록 간결하게 작성
- 응답은 간결하게 유지 (너무 길면 잘립니다)
""")
    ])

    content = response.content

    print(f"✅ Implementation guide generated ({len(content)} characters)")

    # 상태 업데이트
    state["implementation_prompt"] = content
    state["messages"].append({
        "role": "prompt_generator",
        "content": content
    })
    state["current_agent"] = "end"  # 완료

    return state
