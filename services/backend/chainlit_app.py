"""
Chainlit UI for MAS Platform
"""
import chainlit as cl
from workflow import mas_graph
from agents import AgentState
import os
from dotenv import load_dotenv

load_dotenv()


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
async def main(message: cl.Message):
    """메시지 수신 시"""
    
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
    
    # MAS 그래프 실행
    async for event in mas_graph.astream(initial_state):
        for node_name, state in event.items():
            if node_name != "__end__":
                last_message = state["messages"][-1]
                agent_name = last_message["role"]
                agent_content = last_message["content"]
                
                # 에이전트별 아이콘
                agent_icons = {
                    "orchestrator": "🎼",
                    "planning": "📋",
                    "research": "🔍",
                    "backend_developer": "⚙️",
                    "frontend_developer": "🎨",
                    "infrastructure_engineer": "🏗️",
                    "review": "✅"
                }

                icon = agent_icons.get(agent_name, "🤖")
                
                # 스트리밍 업데이트
                response_msg.content += f"\n\n{icon} **{agent_name}**:\n{agent_content}"
                await response_msg.update()
    
    # 최종 업데이트
    await response_msg.update()


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

