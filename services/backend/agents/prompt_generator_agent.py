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


PROMPT_GENERATOR_SYSTEM = """You are the Decision & Recommendation Agent.

## Role
Analyze cluster state and provide user-friendly recommendations in Korean.

## Input
- Planning data: what would be needed if deploying
- Research data: current cluster state, existing resources

## Output Format (Korean Markdown)
Create a user-friendly analysis report:

```markdown
# [도구명] 도입 분석 결과

## 📊 현재 클러스터 상태
- **Kubernetes 버전**: [version]
- **노드 구성**: [nodes info]
- **기존 도구**: [existing tools like ArgoCD, Gitea, etc.]
- **운영 중인 애플리케이션**: [number and types]
- **리소스 사용률**: [if available]

## 💡 권장사항: [도입 추천 / 도입 비추천]

### ✅ 도입을 추천하는 이유 (또는 ❌ 도입을 비추천하는 이유)
1. [이유 1]
2. [이유 2]
3. [이유 3]

### 🔄 대안 (도입 비추천인 경우)
- [대안 1]: [설명]
- [대안 2]: [설명]

### 📌 도입 시 고려사항 (도입 추천인 경우)
- **필요 리소스**: [CPU, Memory]
- **예상 작업 시간**: [time estimate]
- **복잡도**: [난이도]
- **유지보수 부담**: [maintenance effort]

## 🎯 결론
[1-2문장으로 최종 권장사항 요약]

---

## 📁 구현 가이드 (도입하기로 결정한 경우)

### 폴더 구조
\`\`\`
deploy/[tool]/
├── base/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   └── kustomization.yaml
└── overlays/prod/
    └── kustomization.yaml
\`\`\`

### 주요 단계
1. [Step 1 설명]
2. [Step 2 설명]
3. [Step 3 설명]

### 검증 방법
\`\`\`bash
kubectl get pods -n [namespace]
kubectl get svc -n [namespace]
\`\`\`
```

## Guidelines
1. **한국어로 작성** (모든 내용)
2. **명확한 결론** 제시 (추천/비추천)
3. **구체적인 이유** 제공
4. **YAML 코드 제외** (폴더 구조만 간단히)
5. **사용자 친화적** (기술 용어 최소화)
6. 이모지 사용으로 가독성 향상
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
        HumanMessage(content=f"""사용자 요청에 대한 분석 결과를 한국어로 작성해주세요:

**사용자 요청:** {user_request}

**계획 데이터:**
```json
{plan_summary}
```

**클러스터 분석 결과:**
```json
{research_summary}
```

위 정보를 바탕으로:
1. 현재 클러스터 상태 요약
2. 도입 추천/비추천 결정 (명확한 이유와 함께)
3. 대안 제시 (비추천인 경우) 또는 구현 가이드 (추천인 경우)
4. 최종 결론

**중요**: 한국어로 작성하고, YAML 코드는 제외하고, 사용자 친화적으로 작성해주세요.
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
