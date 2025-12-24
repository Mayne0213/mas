"""
Chainlit UI for MAS Platform
"""
import chainlit as cl
from workflow import mas_graph
from agents import AgentState
import os
from dotenv import load_dotenv
import contextvars

load_dotenv()

# Chainlit의 local_steps ContextVar 초기화
try:
    from chainlit.step import local_steps
    local_steps.set([])
except:
    pass


@cl.on_chat_start
async def start():
    """채팅 시작 시"""
    await cl.Message(
        content="☸️ **K8s Infrastructure Planning System v3.0**에 오신 것을 환영합니다!\n\n"
                "당신의 Kubernetes 클러스터 상태를 분석하고 인프라 배포 계획을 수립해드립니다.\n\n"
                "**에이전트 팀**\n"
                "- 🎼 **Orchestrator** (Claude 4.5): 전체 워크플로우 조율\n"
                "- 📋 **Planning Agent** (Claude 4.5): 폴더 구조 & YAML 설계\n"
                "- 🔍 **Research Agent** (Groq): K8s 클러스터 상태 분석\n"
                "- 📝 **Prompt Generator** (Claude 4.5): 구현 가이드 생성\n\n"
                "**사용 예시**\n"
                "```\n"
                "Tekton을 도입하고 싶어\n"
                "Harbor를 배포하려고 해\n"
                "Prometheus를 설치하고 싶어\n"
                "```\n\n"
                "배포하고 싶은 도구를 알려주세요!"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """메시지 수신 시"""
    
    # local_steps ContextVar 초기화
    try:
        from chainlit.step import local_steps
        local_steps.set([])
    except:
        pass
    
    try:
        # 초기 상태
        initial_state: AgentState = {
            "messages": [{"role": "user", "content": message.content}],
            "current_agent": "orchestrator",
            "task_plan": None,
            "research_data": None,
            "implementation_prompt": None,
            "iteration_count": 0,
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
                    user_facing_agents = ["planning", "research", "prompt_generator"]

                    if agent_name in user_facing_agents:
                        # 에이전트별 아이콘
                        agent_icons = {
                            "planning": "📋",
                            "research": "🔍",
                            "prompt_generator": "📝"
                        }

                        agent_display_names = {
                            "planning": "인프라 계획 수립",
                            "research": "클러스터 상태 분석",
                            "prompt_generator": "구현 가이드 생성"
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
                            "planning": "📋 인프라 계획 수립 중...",
                            "research": "🔍 클러스터 상태 분석 중...",
                            "prompt_generator": "📝 구현 가이드 생성 중...",
                            "end": "✨ 완료! 아래 프롬프트를 복사하여 사용하세요."
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
        "prompt_generator": "Prompt Generator (Claude 4.5)"
    }
    return rename_dict.get(orig_author, orig_author)

