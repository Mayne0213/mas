"""
Decision Agent (Claude 4.5)
Planning과 Research 결과를 분석하여 최종 의사결정 (추천/비추천)
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json


# Claude 4.5 모델 초기화
claude_decision = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.5
)


DECISION_SYSTEM = """You are the Decision Agent.

## Role
Analyze planning and research data to make final deployment decision (추천/비추천).

## Input
- Planning data: deployment requirements, resources needed
- Research data: current cluster state, existing tools

## Output Format (Korean Markdown)
Make a clear decision with reasoning:

```markdown
# [도구명] 도입 분석 결과

## 📊 현재 클러스터 상태
- **Kubernetes 버전**: [version]
- **노드 구성**: [nodes info]
- **기존 도구**: [existing tools]
- **리소스 상태**: [available resources]

## 💡 권장사항: [✅ 도입 추천 / ❌ 도입 비추천]

### 결정 이유
1. [이유 1]
2. [이유 2]
3. [이유 3]

### 🔄 대안 (비추천인 경우)
- [대안 1]: [설명]
- [대안 2]: [설명]

### 📌 고려사항 (추천인 경우)
- **필요 리소스**: [CPU, Memory]
- **예상 작업 시간**: [estimate]
- **복잡도**: [level]

## 🎯 결론
[1-2문장으로 최종 권장사항 요약]
```

## Guidelines
1. **한국어로 작성**
2. **명확한 결론** (✅ 추천 or ❌ 비추천)
3. **구체적인 이유** 제공
4. **사용자 친화적** (기술 용어 최소화)
5. 이모지 사용으로 가독성 향상

## Decision Output
Also output a JSON with decision:
{"recommendation": "approve" or "reject", "tool_name": "..."}
"""


def decision_node(state: AgentState) -> AgentState:
    """
    Decision 노드: 최종 의사결정 (추천/비추천)
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
    print(f"Decision Agent - Making final decision")
    print(f"{'='*80}")

    # Claude 호출
    response = claude_decision.invoke([
        SystemMessage(content=DECISION_SYSTEM),
        HumanMessage(content=f"""분석 결과를 바탕으로 최종 의사결정을 내려주세요:

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
2. **도입 추천/비추천 명확히 결정**
3. 구체적인 이유 제시
4. 대안 또는 고려사항 제공
5. 최종 결론

**중요**: 한국어로 작성하고, 사용자 친화적으로 작성해주세요.
마지막에 JSON 형식으로 결정도 포함: {{"recommendation": "approve" or "reject", "tool_name": "..."}}
""")
    ])

    content = response.content

    # 추천/비추천 판단 (JSON 파싱 시도)
    recommendation = "reject"  # 기본값
    try:
        if '{"recommendation"' in content or "```json" in content:
            import re
            json_match = re.search(r'\{[^{}]*"recommendation"[^{}]*\}', content)
            if json_match:
                decision_json = json.loads(json_match.group(0))
                recommendation = decision_json.get("recommendation", "reject")
    except:
        # 텍스트 기반 판단
        if "✅ 도입 추천" in content or "추천" in content:
            recommendation = "approve"

    print(f"✅ Decision made: {recommendation}")

    # 상태 업데이트
    state["decision_report"] = {
        "content": content,
        "recommendation": recommendation
    }
    state["messages"].append({
        "role": "decision",
        "content": content
    })

    # 추천이면 prompt_generator로, 비추천이면 end
    if recommendation == "approve":
        state["current_agent"] = "orchestrator"  # Orchestrator가 prompt_generator로 보냄
    else:
        state["current_agent"] = "end"  # 비추천이면 바로 종료

    return state
