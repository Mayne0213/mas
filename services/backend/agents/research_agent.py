"""
Research Agent (Groq)
정보 수집 및 문서/코드베이스 검색
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os
import json


# Groq 모델 초기화 (OpenAI 호환)
groq_research = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.3
)


RESEARCH_PROMPT = """You are the Research Agent in a Multi-Agent System.

## Role
Collect and analyze information from the host system.

## Environment
- Container: /app/
- Host: Access via nsenter (execute_host tool)
- Kubernetes cluster available on host
- Projects folder: /home/ubuntu/Projects/

## Tools Available

**execute_host(command, use_sudo=False)**: Run commands on the host system
- Use sudo=True for kubectl commands
- Examples: kubectl, find, ls, cat, git, psql

**execute_bash(command)**: Run commands inside the container
- Examples: curl, python, ls /app

## Output Format
Provide results in JSON:
```json
{
  "summary": "Brief summary of findings",
  "findings": [{"category": "...", "data": "..."}],
  "recommendations": ["..."]
}
```

## Instructions
- Use tools freely to gather information
- Try multiple approaches if something fails
- Provide actionable insights and recommendations
"""


def research_node(state: AgentState) -> AgentState:
    """
    Research 노드: 정보 수집
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_needed = task_plan.get("research_needed", [])

    # Groq에 bash 도구 바인딩
    groq_with_tools = groq_research.bind_tools(bash_tools)

    # 연구 요청 구성
    # research_needed가 있으면 사용, 없으면 사용자의 원래 요청 사용
    if research_needed:
        research_request = f"다음 정보를 수집해주세요:\n" + "\n".join(f"- {item}" for item in research_needed)
    else:
        # 사용자의 원래 요청을 찾기
        user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        if user_message:
            research_request = f"사용자 요청: {user_message}\n\n위 요청에 필요한 정보를 수집하고 분석해주세요."
        else:
            research_request = "현재 시스템 상태를 분석하고 필요한 정보를 수집해주세요."

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=RESEARCH_PROMPT),
        HumanMessage(content=research_request)
    ])

    # Tool calls 처리
    tool_outputs = []
    max_iterations = 5  # 최대 반복 횟수 제한
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Tool calls 확인
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call.get('args', {})

                # 도구 실행
                try:
                    # tool_name에 따라 올바른 도구 선택
                    from tools.bash_tool import execute_bash, execute_host
                    if tool_name == "execute_host":
                        tool_func = execute_host
                    else:
                        tool_func = execute_bash
                    tool_result = tool_func.invoke(tool_args)
                    tool_outputs.append(f"\n🔧 **{tool_name}({tool_args.get('command', '')[:100]})**:\n{tool_result}")
                except Exception as e:
                    tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

            # Tool 결과와 함께 재호출
            if tool_outputs:
                tool_context = "\n".join(tool_outputs[-10:])  # 최근 10개만 사용 (너무 길어지지 않도록)
                response = groq_with_tools.invoke([
                    SystemMessage(content=RESEARCH_PROMPT),
                    HumanMessage(content=research_request),
                    HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n추가로 필요한 정보가 있으면 도구를 사용하고, 충분한 정보를 수집했으면 JSON 형식으로 정리해주세요.")
                ])
            else:
                break  # tool_outputs가 비어있으면 종료
        else:
            # tool_calls가 없으면 종료
            break

    # content 추출 (response.content가 없을 수도 있음)
    if hasattr(response, 'content') and response.content:
        content = response.content
    elif tool_outputs:
        # content가 없지만 tool_outputs가 있으면 그것을 사용
        content = "\n".join(tool_outputs) + "\n\n정보 수집 완료. 결과를 정리해주세요."
    else:
        content = "정보 수집을 완료했습니다."

    # Tool outputs를 content에 포함
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

        research_data = json.loads(json_str)
    except Exception:
        research_data = {
            "summary": "정보 수집 완료",
            "findings": [{"category": "raw", "data": content}],
            "recommendations": []
        }

    # 상태 업데이트
    state["research_data"] = research_data
    state["messages"].append({
        "role": "research",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state
