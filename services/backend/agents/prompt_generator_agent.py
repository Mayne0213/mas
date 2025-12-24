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
Generate detailed implementation prompts for other AI assistants (Claude Code, ChatGPT, etc.).

## Input
- Planning data: folder structure, required resources
- Research data: cluster state, existing tools
- Decision: deployment approved (추천)

## Output Format (Markdown)
Create a comprehensive implementation guide that another AI can use:

```markdown
# [도구명] Kubernetes 배포 구현 가이드

## 📋 프로젝트 개요
- **목표**: [도구] Kubernetes 클러스터에 배포
- **환경**: Kubernetes v[version], [nodes] 노드
- **사전 요구사항**: [prerequisites]

## 📁 폴더 구조
다음과 같은 디렉토리 구조를 생성하세요:
\`\`\`
deploy/[tool]/
├── base/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── rbac.yaml
│   └── kustomization.yaml
└── overlays/
    └── prod/
        ├── resource-limits.yaml
        └── kustomization.yaml
\`\`\`

## 🔧 구현 단계

### Step 1: Namespace 및 RBAC 생성
**파일**: `deploy/[tool]/base/namespace.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: [namespace]
  labels:
    app: [tool]
```

**파일**: `deploy/[tool]/base/rbac.yaml`
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: [tool]-sa
  namespace: [namespace]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: [tool]-role
rules:
  - apiGroups: [""]
    resources: ["pods", "services"]
    verbs: ["get", "list", "watch"]
```

### Step 2: Deployment 생성
**파일**: `deploy/[tool]/base/deployment.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: [tool]
  namespace: [namespace]
spec:
  replicas: [replicas]
  selector:
    matchLabels:
      app: [tool]
  template:
    metadata:
      labels:
        app: [tool]
    spec:
      serviceAccountName: [tool]-sa
      containers:
      - name: [tool]
        image: [image]:[tag]
        ports:
        - containerPort: [port]
        resources:
          requests:
            memory: "[memory]"
            cpu: "[cpu]"
          limits:
            memory: "[memory_limit]"
            cpu: "[cpu_limit]"
```

### Step 3: Service 및 Ingress 생성
[... 계속 작성]

### Step 4: Kustomize 설정
[... 계속 작성]

## ✅ 검증 및 배포

### 배포 명령어
```bash
# Dry-run으로 검증
kubectl apply -k deploy/[tool]/overlays/prod --dry-run=client

# 실제 배포
kubectl apply -k deploy/[tool]/overlays/prod

# 상태 확인
kubectl get pods -n [namespace]
kubectl get svc -n [namespace]
kubectl logs -f deployment/[tool] -n [namespace]
```

### 검증 체크리스트
- [ ] Pod가 Running 상태인지 확인
- [ ] Service가 올바른 포트로 노출되는지 확인
- [ ] Ingress가 정상 작동하는지 확인
- [ ] 로그에 에러가 없는지 확인

## 📌 주요 고려사항
- **리소스 제한**: [cluster 상황에 맞춘 권장사항]
- **보안**: [RBAC, NetworkPolicy 등]
- **모니터링**: [ServiceMonitor, 로그 수집 등]
- **백업**: [설정 백업 방법]

## 🔗 참고 자료
- [도구] 공식 문서: [URL]
- Kubernetes 배포 가이드: [URL]
```

## Guidelines
1. **실행 가능한 YAML 예시** 포함
2. **단계별 구현 가이드** 제공
3. **검증 명령어** 포함
4. **클러스터 상황에 맞춘 권장사항** (Research 데이터 활용)
5. 다른 AI가 바로 실행할 수 있도록 구체적으로 작성
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
1. 실행 가능한 YAML 파일 예시 작성
2. 단계별 구현 가이드 제공
3. 클러스터 상황에 맞춘 리소스 설정 권장
4. 배포 및 검증 명령어 포함
5. 다른 AI가 바로 실행할 수 있도록 구체적으로 작성

**중요**: Markdown 형식으로 작성하고, 실제로 동작하는 YAML 코드를 포함해주세요.
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
