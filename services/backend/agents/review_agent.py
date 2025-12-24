"""
Review & Test Agent (Claude)
코드 리뷰, 품질 검증, 테스트 전략 수립
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os
import json


# Claude 모델 초기화 (리뷰는 고품질 모델 사용)
claude_review = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.3
)


REVIEW_PROMPT = """당신은 Multi-Agent System의 **Review & Test Agent**입니다.

## 역할
- 생성된 코드의 품질 검증
- 보안 취약점 검사
- 성능 및 확장성 평가
- 테스트 전략 수립 및 실행
- 개선 사항 제안

## 사용 가능한 도구
**execute_bash**: 코드 검증을 위한 bash 명령어 실행
- 테스트 실행: pytest, npm test, go test
- 린터 실행: pylint, eslint, golangci-lint
- 빌드 검증: docker build, npm run build
- 배포 확인: kubectl get pods, kubectl logs

## 검토 항목

### 1. 코드 품질
- 가독성 및 유지보수성
- 네이밍 컨벤션
- 코드 중복 제거
- 에러 처리

### 2. 보안
- SQL Injection
- XSS (Cross-Site Scripting)
- CSRF
- 인증/인가 로직
- 민감 정보 노출

### 3. 성능
- 쿼리 최적화
- 캐싱 전략
- 비동기 처리
- 리소스 사용

### 4. 테스트
- 단위 테스트 필요성
- 통합 테스트 시나리오
- E2E 테스트 계획

### 5. 인프라 (Kubernetes YAML)
- Resource limits/requests
- Liveness/Readiness probes
- Security context
- Network policies

## 출력 형식 (JSON)
반드시 다음 JSON 형식으로 출력하세요:
```json
{
  "approved": true/false,
  "overall_score": 85,
  "summary": "전체 평가 요약",
  "issues": [
    {
      "severity": "high|medium|low",
      "category": "security|performance|quality|test",
      "description": "문제 설명",
      "recommendation": "개선 방안"
    }
  ],
  "strengths": ["강점 1", "강점 2"],
  "next_steps": ["다음 단계 1", "다음 단계 2"]
}
```

## 승인 기준
- **approved: true**: 심각한 문제 없음, 배포 가능
- **approved: false**: 중대한 보안/품질 이슈, 재작업 필요

## 점수 기준
- 90-100: Excellent
- 80-89: Good
- 70-79: Acceptable
- 60-69: Needs Improvement
- < 60: Major Issues
"""


def review_node(state: AgentState) -> AgentState:
    """
    Review 노드: 코드 리뷰 및 품질 검증
    """
    messages = state["messages"]
    code_outputs = state.get("code_outputs", {})
    task_plan = state.get("task_plan", {})

    # 코드 리뷰 요청 구성
    code_summary = "\n\n".join([
        f"### {agent_type.upper()}\n{code}"
        for agent_type, code in code_outputs.items()
    ])

    review_request = f"""
작업 계획: {task_plan.get('summary', '')}
성공 기준: {task_plan.get('success_criteria', [])}

생성된 코드:
{code_summary}

위 코드를 검토하고, 필요시 테스트를 실행한 후 JSON 형식으로 피드백을 제공해주세요.
"""

    # Claude에 bash 도구 바인딩
    claude_with_tools = claude_review.bind_tools(bash_tools)

    # Claude 호출
    response = claude_with_tools.invoke([
        SystemMessage(content=REVIEW_PROMPT),
        HumanMessage(content=review_request)
    ])

    # Tool calls 처리
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            try:
                # tool_name에 따라 올바른 도구 선택
                from tools.bash_tool import execute_bash, execute_host
                if tool_name == "execute_host":
                    tool_func = execute_host
                else:
                    tool_func = execute_bash
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **Review {tool_name}({tool_args.get('command', '')[:50]}...)**:\n{tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Tool 결과와 함께 재호출
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = claude_review.invoke([
                SystemMessage(content=REVIEW_PROMPT),
                HumanMessage(content=review_request),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n이제 JSON 형식으로 최종 리뷰를 제공해주세요.")
            ])

    content = response.content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # JSON 파싱 시도
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content

        review_feedback = json.loads(json_str)
    except Exception as e:
        review_feedback = {
            "approved": False,
            "overall_score": 50,
            "summary": "리뷰 파싱 실패",
            "issues": [{"severity": "high", "category": "quality", "description": f"JSON 파싱 에러: {str(e)}", "recommendation": "재검토 필요"}],
            "strengths": [],
            "next_steps": ["피드백 재생성"]
        }

    # 상태 업데이트
    state["review_feedback"] = review_feedback
    state["is_approved"] = review_feedback.get("approved", False)
    state["messages"].append({
        "role": "review",
        "content": content
    })

    # 승인되지 않았고 반복 횟수가 3 미만이면 재작업
    if not state["is_approved"] and state["iteration_count"] < 3:
        state["iteration_count"] += 1
        state["current_agent"] = "orchestrator"  # 재작업을 위해 orchestrator로
    else:
        state["current_agent"] = "end"  # 승인되었거나 최대 반복 도달

    return state
