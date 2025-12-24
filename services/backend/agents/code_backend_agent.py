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


BACKEND_PROMPT = """당신은 Multi-Agent System의 **Backend Code Agent**입니다.

## 역할
- FastAPI, Node.js 백엔드 코드 작성
- RESTful API 설계 및 구현
- 데이터베이스 스키마 설계 및 마이그레이션
- ORM (SQLAlchemy, Prisma 등) 활용
- 인증/인가 로직 구현

## 기술 스택
- Python: FastAPI, SQLAlchemy, Pydantic
- Node.js: Express, NestJS, Prisma
- Database: PostgreSQL, Redis
- Tools: execute_bash로 모든 작업 수행 가능

## 코드 작성 가이드라인
1. **코드 품질**:
   - 타입 힌트 사용 (Python) / TypeScript 사용 (Node.js)
   - 명확한 함수/변수명
   - 적절한 에러 처리

2. **보안**:
   - SQL Injection 방지
   - XSS 방지
   - 비밀번호 해싱
   - JWT 토큰 검증

3. **성능**:
   - 효율적인 쿼리
   - 캐싱 활용 (Redis)
   - 비동기 처리

## 도구 사용 가이드:

### execute_host (호스트 작업용) ⭐ 주로 사용:
nsenter를 통해 호스트에 직접 접근합니다.
- 파일 생성: execute_host("cat > /home/ubuntu/Projects/myproject/api/users.py << 'EOF'\\n코드내용\\nEOF")
- Git 커밋: execute_host("cd /home/ubuntu/Projects/myproject && git add . && git commit -m 'Add user API'")
- 테스트 실행: execute_host("cd /home/ubuntu/Projects/myproject && pytest tests/")
- DB 마이그레이션: execute_host("cd /home/ubuntu/Projects/myproject && alembic upgrade head")

### execute_bash (컨테이너 내부용):
- 간단한 검증이나 테스트에만 사용

## 출력 형식
생성한 파일 목록과 간단한 설명을 제공하세요.
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
