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
Create a deployment guide following existing patterns:

```markdown
# [도구명] Kubernetes 배포 구현 가이드

## 🌐 환경 정보
- **서버**: oracle-master
- **Projects 루트**: `/home/ubuntu/Projects/`
- **Kubernetes**: v[version]

## 📍 배치 위치
\`\`\`
/home/ubuntu/Projects/[category]/[tool-name]/
\`\`\`
**분류 기준**: [이 도구가 왜 이 카테고리에 속하는지 설명]

**동일 카테고리 예시**:
- `[category]/[example1]/` - [설명]
- `[category]/[example2]/` - [설명]

## 📂 필수 폴더 구조
\`\`\`
/home/ubuntu/Projects/[category]/[tool-name]/
├── argocd/
│   └── [tool-name].yaml    # ArgoCD Application 정의
├── helm-values/            # (선택) Helm 사용 시
│   └── [tool-name].yaml
├── vault/                  # (필요시) 민감 정보
│   └── *.yaml
└── kustomization.yaml      # 리소스 목록
\`\`\`

## 📋 파일별 역할

### 1. `argocd/[tool-name].yaml`
**용도**: ArgoCD Application 리소스 정의
- `spec.source.repoURL`: Git 저장소 URL
- `spec.source.path`: `[category]/[tool-name]`
- `spec.destination.namespace`: 배포 네임스페이스
- `spec.syncPolicy`: 자동 동기화 설정

### 2. `helm-values/[tool-name].yaml` (선택)
**용도**: Helm chart 사용 시 커스텀 values
- Helm 배포 시에만 필요
- 순수 manifest 배포 시 생략 가능

### 3. `vault/` (필요시)
**용도**: 민감 정보를 위한 ExternalSecret 리소스
- Vault에서 자동 주입
- 예: passwords, API keys, tokens
- **중요**: 평문 Secret 리소스 사용 금지

### 4. `kustomization.yaml`
**용도**: 배포할 모든 리소스 목록
- `resources:` 섹션에 모든 YAML 파일 나열
- namespace, labels 등 공통 설정

## 🔄 기존 패턴 준수 사항

1. **ArgoCD 통합 (필수)**
   - 모든 앱은 ArgoCD로 관리
   - `/home/ubuntu/Projects/[category]/kustomization.yaml`에 추가 필요

2. **Vault ExternalSecret (권장)**
   - 민감 정보는 Vault 사용
   - 평문 Secret 금지

3. **일관된 네이밍 (필수)**
   - 파일명: `[tool-name].yaml`
   - 리소스 이름: `[tool-name]-*`

## 📚 참고 예시

**동일 카테고리 프로젝트 구조 참고**:
```bash
/home/ubuntu/Projects/applications/gitea/
├── argocd/gitea.yaml
├── helm-values/gitea.yaml
├── vault/gitea-admin-secret.yaml
└── kustomization.yaml
```

## 🚀 AI 생성 지침

위 구조와 패턴을 준수하여:

1. **적절한 카테고리 선택**
   - applications, cluster-infrastructure, monitoring, databases 중 선택
   - 선택 이유 명확히 설명

2. **필수 파일 목록**
   - argocd/[tool-name].yaml
   - kustomization.yaml
   - 필요 시: helm-values/, vault/

3. **파일 역할만 설명**
   - 세부 YAML 내용은 AI가 생성
   - 구조와 필수 필드만 제시

4. **기존 패턴 준수**
   - ArgoCD, Vault, Kustomize 통합
   - 평문 Secret 사용 금지

## 🔍 배포 전 체크리스트
- [ ] 올바른 카테고리에 배치
- [ ] argocd/ 폴더 존재
- [ ] kustomization.yaml 작성
- [ ] 민감 정보는 Vault 사용
- [ ] Git commit 및 push
- [ ] ArgoCD 자동 배포 확인
```

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
