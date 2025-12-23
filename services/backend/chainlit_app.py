"""
Chainlit UI for MAS Platform
"""
import chainlit as cl
from agents import mas_graph, AgentState
import os
from dotenv import load_dotenv

load_dotenv()


@cl.on_chat_start
async def start():
    """채팅 시작 시"""
    await cl.Message(
        content="🤖 **Multi-Agent System**에 오신 것을 환영합니다!\n\n"
                "저는 다음 전문가 팀과 함께 작업합니다:\n\n"
                "- 🎼 **Claude Code**: 총괄 조율자 & DevOps 전문가\n"
                "- ⚙️ **Groq Backend**: 백엔드 개발자\n"
                "- 🎨 **Groq Frontend**: 프론트엔드 개발자\n"
                "- 📊 **Groq SRE**: 모니터링 & 성능 전문가\n"
                "- 📝 **Groq YAML Manager**: Kubernetes YAML 파일 관리\n\n"
                "무엇을 도와드릴까요?"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """메시지 수신 시"""
    
    # 초기 상태
    initial_state: AgentState = {
        "messages": [{"role": "user", "content": message.content}],
        "current_agent": "orchestrator",
        "task_type": "",
        "result": {}
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
                    "backend_developer": "⚙️",
                    "frontend_developer": "🎨",
                    "sre_specialist": "📊",
                    "yaml_manager": "📝"
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
        "orchestrator": "Claude Code (Orchestrator)",
        "backend_developer": "Groq Backend Dev",
        "frontend_developer": "Groq Frontend Dev",
        "sre_specialist": "Groq SRE",
        "yaml_manager": "Groq YAML Manager"
    }
    return rename_dict.get(orig_author, orig_author)

