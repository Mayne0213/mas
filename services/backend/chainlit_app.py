"""
Chainlit UI for MAS Platform
"""
import chainlit as cl
from workflow import mas_graph
from agents import AgentState
import os
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

# Chainlit의 자동 Step 래핑 비활성화
def disable_auto_step(func):
    """Disable Chainlit's automatic step wrapping"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    wrapper.__wrapped__ = func
    # Chainlit이 확인하는 속성 설정
    wrapper._no_step = True
    return wrapper


@cl.on_chat_start
async def start():
    """채팅 시작 시"""
    await cl.Message(
        content="🤖 **Multi-Agent System v2.0**에 오신 것을 환영합니다!\n\n"
                "저는 다음 전문가 팀과 함께 작업합니다:\n\n"
                "**계획 & 조율**\n"
                "- 🎼 **Orchestrator** (Claude 4.5): 전체 워크플로우 조율\n"
                "- 📋 **Planning Agent** (Claude 4.5): 작업 계획 수립\n\n"
                "**정보 수집**\n"
                "- 🔍 **Research Agent** (Groq): 정보 수집 및 분석\n\n"
                "**코드 작성**\n"
                "- ⚙️ **Backend Agent** (Groq): 백엔드 개발\n"
                "- 🎨 **Frontend Agent** (Groq): 프론트엔드 개발\n"
                "- 🏗️ **Infrastructure Agent** (Groq): K8s/DevOps\n\n"
                "**품질 보증**\n"
                "- ✅ **Review Agent** (Claude): 코드 리뷰 & 테스트\n\n"
                "무엇을 도와드릴까요?"
    ).send()


@cl.on_message
@disable_auto_step
async def main(message: cl.Message):
    """메시지 수신 시"""
    
    try:
        # 초기 상태
        initial_state: AgentState = {
            "messages": [{"role": "user", "content": message.content}],
            "current_agent": "orchestrator",
            "task_plan": None,
            "research_data": None,
            "code_outputs": {},
            "review_feedback": None,
            "iteration_count": 0,
            "is_approved": False,
            "error": None
        }
        
        # 응답 메시지 생성
        response_msg = cl.Message(content="")
        await response_msg.send()
        
        # 상태 표시용 메시지
        status_msg = cl.Message(content="⏳ 작업 중...")
        await status_msg.send()

        # MAS 그래프 실행
        async for event in mas_graph.astream(initial_state):
        for node_name, state in event.items():
            if node_name != "__end__":
                last_message = state["messages"][-1]
                agent_name = last_message["role"]
                agent_content = last_message["content"]

                # 사용자에게 보여줄 에이전트만 필터링
                user_facing_agents = ["planning", "research", "backend_developer",
                                     "frontend_developer", "infrastructure_engineer", "review"]

                if agent_name in user_facing_agents:
                    # 에이전트별 아이콘
                    agent_icons = {
                        "planning": "📋",
                        "research": "🔍",
                        "backend_developer": "⚙️",
                        "frontend_developer": "🎨",
                        "infrastructure_engineer": "🏗️",
                        "review": "✅"
                    }

                    agent_display_names = {
                        "planning": "계획 수립",
                        "research": "정보 수집",
                        "backend_developer": "백엔드 개발",
                        "frontend_developer": "프론트엔드 개발",
                        "infrastructure_engineer": "인프라 구성",
                        "review": "코드 리뷰"
                    }

                    icon = agent_icons.get(agent_name, "🤖")
                    display_name = agent_display_names.get(agent_name, agent_name)

                    # 내부 라우팅 정보 제거 (NEXT_AGENT, REASON 등)
                    cleaned_content = agent_content
                    for keyword in ["NEXT_AGENT:", "REASON:", "MESSAGE:"]:
                        if keyword in cleaned_content:
                            # 라우팅 정보가 포함된 경우 해당 부분 제거
                            lines = cleaned_content.split("\n")
                            cleaned_lines = [line for line in lines if not line.strip().startswith(keyword.replace(":", ""))]
                            cleaned_content = "\n".join(cleaned_lines)

                    # 스트리밍 업데이트
                    response_msg.content += f"\n\n{icon} **{display_name}**:\n{cleaned_content.strip()}"
                    await response_msg.update()

                elif agent_name == "orchestrator":
                    # Orchestrator는 간단한 상태 메시지만 표시
                    current_agent = state.get("current_agent", "")
                    status_icons = {
                        "planning": "📋 계획 수립 중...",
                        "research": "🔍 정보 수집 중...",
                        "code_backend": "⚙️ 백엔드 코드 작성 중...",
                        "code_frontend": "🎨 프론트엔드 코드 작성 중...",
                        "code_infrastructure": "🏗️ 인프라 구성 중...",
                        "review": "✅ 코드 검토 중...",
                        "end": "✨ 완료!"
                    }
                    status_text = status_icons.get(current_agent, "⏳ 작업 중...")
                    status_msg.content = status_text
                    await status_msg.update()

        # 상태 메시지 제거
        await status_msg.remove()
        
        # 최종 업데이트
        await response_msg.update()
        
    except Exception as e:
        error_msg = f"❌ 오류가 발생했습니다: {str(e)}"
        await cl.Message(content=error_msg).send()
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()


@cl.on_settings_update
async def setup_agent(settings):
    """설정 업데이트"""
    print(f"Settings updated: {settings}")


# 사이드바 설정
@cl.author_rename
def rename(orig_author: str):
    """에이전트 이름 매핑"""
    rename_dict = {
        "orchestrator": "Orchestrator (Claude 4.5)",
        "planning": "Planning Agent (Claude 4.5)",
        "research": "Research Agent (Groq)",
        "backend_developer": "Backend Agent (Groq)",
        "frontend_developer": "Frontend Agent (Groq)",
        "infrastructure_engineer": "Infrastructure Agent (Groq)",
        "review": "Review Agent (Claude)"
    }
    return rename_dict.get(orig_author, orig_author)

