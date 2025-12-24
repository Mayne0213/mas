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


ORCHESTRATOR_PROMPT = """You are the Orchestrator of a K8s Analysis & Decision System.

## Role
Determine request type and route to appropriate agents.

## Request Types

### Type 1: Information Query (정보 조회)
Keywords: "알려줘", "조회", "확인", "보여줘", "찾아줘", "검색", "상태", "비밀번호", "목록", "리스트"
Examples:
- "PostgreSQL 비밀번호 알려줘"
- "현재 Pod 상태 확인해줘"
- "Secret 목록 보여줘"
Workflow: research → end

### Type 2: Deployment Decision (도입 결정)
Keywords: "도입", "설치", "배포", "필요", "결정", "추천", "분석", "사용"
Examples:
- "Tekton 도입할까?"
- "Harbor가 필요한지 분석해줘"
Workflow: planning → research → prompt_generator → end

## Available Agents
- planning: Plan deployment requirements (deployment_decision only)
- research: Analyze cluster state or retrieve information
- decision: Make final decision (추천/비추천) (deployment_decision only)
- prompt_generator: Generate implementation guide for other AI (deployment_decision, only if approved)
- end: Complete the task

## Decision Logic

**First, determine request_type (첫 호출 시만):**
- If user wants information → request_type = "information_query"
- If user wants deployment decision → request_type = "deployment_decision"

**Then route based on request_type:**

### For information_query:
- Current state: start → NEXT_AGENT: research
- Current state: research done → NEXT_AGENT: end

### For deployment_decision:
- Current state: start → NEXT_AGENT: planning
- Current state: planning done → NEXT_AGENT: research
- Current state: research done → NEXT_AGENT: decision
- Current state: decision done (추천) → NEXT_AGENT: prompt_generator
- Current state: decision done (비추천) → NEXT_AGENT: end
- Current state: prompt_generator done → NEXT_AGENT: end

Check state.get("task_plan"), state.get("research_data"), state.get("decision_report"), state.get("implementation_prompt") to determine current progress.

## Output Format
REQUEST_TYPE: <information_query|deployment_decision>
NEXT_AGENT: <agent_name>
REASON: <brief reason>

Analyze user intent carefully to choose the correct request type.
"""


def orchestrator_node(state: AgentState) -> AgentState:
    """
    Orchestrator 노드: 전체 워크플로우 조율
    """
    messages = state["messages"]
    iteration_count = state.get("iteration_count", 0)

    # 컨텍스트 구성
    context_parts = [f"현재 반복 횟수: {iteration_count}/2"]

    if state.get("task_plan"):
        context_parts.append(f"✅ 계획 수립 완료")

    if state.get("research_data"):
        context_parts.append(f"✅ 클러스터 분석 완료")

    if state.get("implementation_prompt"):
        context_parts.append(f"✅ 구현 프롬프트 생성 완료")

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

    # 요청 타입 파싱
    request_type = state.get("request_type")  # 기존 값 유지
    if "REQUEST_TYPE:" in content and not request_type:
        for line in content.split("\n"):
            if line.startswith("REQUEST_TYPE:"):
                request_type = line.split(":")[1].strip()
                state["request_type"] = request_type
                break

    # 다음 에이전트 파싱
    next_agent = "planning"  # 기본값
    if "NEXT_AGENT:" in content:
        for line in content.split("\n"):
            if line.startswith("NEXT_AGENT:"):
                next_agent = line.split(":")[1].strip()
                break

    # request_type에 따른 라우팅 보정
    if request_type == "information_query":
        # 정보 조회: Planning 건너뛰기
        if next_agent == "planning":
            next_agent = "research"
    elif request_type == "deployment_decision":
        # 의사결정: 순서 보장 (planning → research → decision → prompt_generator(추천시만) → end)
        task_plan = state.get("task_plan")
        research_data = state.get("research_data")
        decision_report = state.get("decision_report")
        implementation_prompt = state.get("implementation_prompt")

        if not task_plan:
            next_agent = "planning"
        elif not research_data:
            next_agent = "research"
        elif not decision_report:
            next_agent = "decision"
        elif decision_report and decision_report.get("recommendation") == "approve" and not implementation_prompt:
            next_agent = "prompt_generator"
        else:
            next_agent = "end"

    # 메시지 추가
    state["messages"].append({
        "role": "orchestrator",
        "content": content
    })
    state["current_agent"] = next_agent

    return state
