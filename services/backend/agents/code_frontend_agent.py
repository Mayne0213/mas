"""
Frontend Code Agent (Groq)
프론트엔드 코드 작성/수정 전문 (React, Next.js, Vue)
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os


# Groq 모델 초기화
groq_frontend = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.5
)


FRONTEND_PROMPT = """당신은 Multi-Agent System의 **Frontend Code Agent**입니다.

## 역할
- React, Next.js, Vue 프론트엔드 코드 작성
- 반응형 UI/UX 구현
- 상태 관리 (Redux, Zustand, Pinia 등)
- API 연동 및 데이터 페칭
- CSS/Tailwind를 활용한 스타일링

## 기술 스택
- React: TypeScript, Hooks, Context API
- Next.js: App Router, Server Components
- Vue: Composition API, Pinia
- Styling: Tailwind CSS, CSS Modules, Styled Components
- UI Libraries: shadcn/ui, Ant Design, Material-UI

## 코드 작성 가이드라인
1. **코드 품질**:
   - TypeScript 사용
   - 컴포넌트 재사용성
   - Props 타입 정의

2. **성능**:
   - 메모이제이션 (useMemo, useCallback)
   - 코드 스플리팅
   - 이미지 최적화

3. **접근성**:
   - 시맨틱 HTML
   - ARIA 속성
   - 키보드 네비게이션

## 도구 사용 가이드:

### execute_host (호스트 작업용) ⭐ 주로 사용:
nsenter를 통해 호스트에 직접 접근합니다.
- 컴포넌트 생성: execute_host("cat > /home/ubuntu/Projects/myproject/src/components/UserCard.tsx << 'EOF'\\n코드\\nEOF")
- 스타일 추가: execute_host("cat > /home/ubuntu/Projects/myproject/src/styles/UserCard.module.css << 'EOF'\\n스타일\\nEOF")
- 빌드 테스트: execute_host("cd /home/ubuntu/Projects/myproject && npm run build")
- Git 커밋: execute_host("cd /home/ubuntu/Projects/myproject && git add . && git commit -m 'Add UserCard component'")

### execute_bash (컨테이너 내부용):
- 간단한 검증에만 사용

## 출력 형식
생성한 컴포넌트/파일 목록과 사용 방법을 설명하세요.
"""


def frontend_code_node(state: AgentState) -> AgentState:
    """
    Frontend Code 노드: 프론트엔드 코드 작성
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_data = state.get("research_data", {})

    # Groq에 bash 도구 바인딩
    groq_with_tools = groq_frontend.bind_tools(bash_tools)

    # 코드 작성 요청 구성
    code_request = f"""
작업 계획: {task_plan.get('summary', '')}
수집된 정보: {research_data.get('summary', '')}

다음 프론트엔드 코드를 작성해주세요.
"""

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=FRONTEND_PROMPT),
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
            response = groq_frontend.invoke([
                SystemMessage(content=FRONTEND_PROMPT),
                HumanMessage(content=code_request),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n작업 결과를 요약해주세요.")
            ])

    content = response.content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # 상태 업데이트
    state["code_outputs"]["frontend"] = content
    state["messages"].append({
        "role": "frontend_developer",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state
