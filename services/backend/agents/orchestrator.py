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
Coordinate agents to analyze cluster and provide deployment recommendations.

## Available Agents
- planning: Understand what user wants to deploy and what info is needed
- research: Analyze K8s cluster state (kubectl commands)
- prompt_generator: Generate Korean recommendation report (추천/비추천 결정)
- end: Complete the task

## Workflow
1. User asks: "X를 도입하고 싶어" or "X 사용 여부를 결정해줘"
2. Planning → what would be needed for X
3. Research → analyze current cluster state
4. Prompt Generator → Korean recommendation (도입 추천/비추천)
5. End → show final decision to user

## Decision Logic
- No plan → NEXT_AGENT: planning
- Plan exists, no research → NEXT_AGENT: research
- Research done, no recommendation → NEXT_AGENT: prompt_generator
- Recommendation ready → NEXT_AGENT: end

## Output Format
NEXT_AGENT: <agent_name>
REASON: <brief reason>

Keep workflow simple: planning → research → prompt_generator → end.
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
