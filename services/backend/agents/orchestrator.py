"""
Orchestrator Agent (Claude 4.5)
전체 조율 및 최종 의사결정
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os


# Claude 4.5 모델 초기화
claude_orchestrator = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.7
)


ORCHESTRATOR_PROMPT = """당신은 Multi-Agent System의 **총괄 조율자(Orchestrator)**입니다.

## ⚠️ 시스템 환경
- **실행 위치**: Docker 컨테이너 (/app/)
- **호스트 접근**: nsenter를 통한 직접 접근 (SSH 불필요)
- **Projects 경로**: /home/ubuntu/Projects/ (oracle-master 서버)
- **Kubernetes**: kubectl은 호스트에서만 작동 (sudo 필요)

## 역할
- 사용자 요청을 분석하고 적절한 에이전트에게 작업 위임
- 각 에이전트의 결과를 검토하고 다음 단계 결정
- 최종 출력물의 품질 보증
- 에러 발생 시 복구 전략 수립
- 필요시 직접 명령어 실행 (간단한 조회/검증)

## 자동 탐색 및 분석 요청 처리

사용자가 다음과 같은 요청을 하면:
- "폴더/파일 찾아서 해줘"
- "현재 k8s 상태 분석해서 해결책 제시해줘"
- "Projects에 어떤 레포가 있는지 확인해줘"
- "문제를 찾아서 해결해줘"

**즉시 Research Agent에게 위임**하고, Research Agent가 자동으로 탐색하고 분석하도록 지시하세요.
Research Agent는 경로를 모르더라도 자동으로 찾아서 작업할 수 있습니다.

## 사용 가능한 도구

### execute_host (호스트 접근용) ⭐ 주로 사용
nsenter를 통해 호스트 네임스페이스에 직접 접근합니다.
- Kubernetes: execute_host("kubectl get pods -n mas", use_sudo=True)
- Projects: execute_host("ls -la /home/ubuntu/Projects")
- Git: execute_host("cd /home/ubuntu/Projects/mas && git status")

### execute_bash (컨테이너 내부용)
- 컨테이너 파일 조회: execute_bash("ls -la /app")
- 간단한 검증: execute_bash("python --version")

## 워크플로우
1. 사용자 요청 분석
2. Planning Agent에게 작업 계획 수립 요청
3. 계획에 따라 Research → Code → Review 순환 관리
4. Review Agent 피드백 기반 재작업 여부 결정 (최대 3회 반복)
5. 최종 승인 시 사용자에게 결과 전달

## 다음 단계 결정 기준
- planning: 아직 계획이 없는 경우
- research: 정보 수집이 필요한 경우
- code_backend: 백엔드 코드 작성 필요
- code_frontend: 프론트엔드 코드 작성 필요
- code_infrastructure: Kubernetes/YAML/인프라 작업 필요
- review: 코드 검토 및 품질 검증 필요
- end: 작업 완료 또는 최대 반복 도달

## 출력 형식
다음 에이전트와 이유를 명시하세요:
NEXT_AGENT: planning
REASON: 이유 설명
MESSAGE: 해당 에이전트에게 전달할 메시지

## 주의사항
- 반복 횟수(iteration_count) 확인 (최대 3회)
- Review Agent의 피드백을 신중히 검토
- 에러 발생 시 적절한 복구 조치
"""


def orchestrator_node(state: AgentState) -> AgentState:
    """
    Orchestrator 노드: 전체 워크플로우 조율
    """
    messages = state["messages"]
    iteration_count = state.get("iteration_count", 0)

    # 컨텍스트 구성
    context_parts = [f"현재 반복 횟수: {iteration_count}/3"]

    if state.get("task_plan"):
        context_parts.append(f"작업 계획: {state['task_plan']}")

    if state.get("research_data"):
        context_parts.append(f"수집된 정보: {state['research_data']}")

    if state.get("code_outputs"):
        context_parts.append(f"생성된 코드: {state['code_outputs']}")

    if state.get("review_feedback"):
        context_parts.append(f"리뷰 피드백: {state['review_feedback']}")

    context = "\n".join(context_parts)

    # 사용자 요청
    user_request = messages[-1]["content"] if messages else ""

    # Claude에 bash 도구 바인딩
    claude_with_tools = claude_orchestrator.bind_tools(bash_tools)

    # Claude 호출
    response = claude_with_tools.invoke([
        SystemMessage(content=ORCHESTRATOR_PROMPT),
        HumanMessage(content=f"사용자 요청: {user_request}\n\n현재 상태:\n{context}")
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
                tool_outputs.append(f"\n🔧 **Orchestrator {tool_name}({tool_args.get('command', '')[:50]}...)**:\n{tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Tool 결과와 함께 재호출
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = claude_orchestrator.invoke([
                SystemMessage(content=ORCHESTRATOR_PROMPT),
                HumanMessage(content=f"사용자 요청: {user_request}\n\n현재 상태:\n{context}"),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])

    content = response.content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # 다음 에이전트 파싱
    next_agent = "planning"  # 기본값
    if "NEXT_AGENT:" in content:
        for line in content.split("\n"):
            if line.startswith("NEXT_AGENT:"):
                next_agent = line.split(":")[1].strip()
                break

    # 메시지 추가
    state["messages"].append({
        "role": "orchestrator",
        "content": content
    })
    state["current_agent"] = next_agent

    return state
