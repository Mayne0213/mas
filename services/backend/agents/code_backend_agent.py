"""
Backend Code Agent (Groq)
백엔드 코드 작성/수정 전문 (FastAPI, Node.js, Database)
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os


# Groq 모델 초기화
groq_backend = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.5
)


BACKEND_PROMPT = """You are the Backend Code Agent.

## Role
Write backend code (FastAPI, Node.js, databases).

## Tools
- execute_host: Write files to /home/ubuntu/Projects/, run git commands
- execute_bash: Test and validate

## Important
- After modifying files: git add, commit, and push (ArgoCD deploys automatically)
- Write clean, secure code with proper error handling
"""


def backend_code_node(state: AgentState) -> AgentState:
    """
    Backend Code 노드: 백엔드 코드 작성
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_data = state.get("research_data", {})

    # Groq에 bash 도구 바인딩
    groq_with_tools = groq_backend.bind_tools(bash_tools)

    # 코드 작성 요청 구성
    code_request = f"""
작업 계획: {task_plan.get('summary', '')}
수집된 정보: {research_data.get('summary', '')}

다음 백엔드 코드를 작성해주세요.
"""

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=BACKEND_PROMPT),
        HumanMessage(content=code_request)
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
                tool_outputs.append(f"\n🔧 **{tool_name}({tool_args.get('command', '')[:50]}...)**:\n{tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Tool 결과와 함께 재호출
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_backend.invoke([
                SystemMessage(content=BACKEND_PROMPT),
                HumanMessage(content=code_request),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n작업 결과를 요약해주세요.")
            ])

    content = response.content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # 상태 업데이트
    state["code_outputs"]["backend"] = content
    state["messages"].append({
        "role": "backend_developer",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state
