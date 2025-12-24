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
        content="☸️ **K8s 인프라 분석 & 의사결정 시스템**에 오신 것을 환영합니다!\n\n"
                "클러스터를 분석하고, 도구 도입 여부를 결정해드립니다.\n\n"
                "**어떻게 작동하나요?**\n"
                "1. 📋 도구 분석 → 2. 🔍 클러스터 상태 확인 → 3. 💡 추천/비추천 결정\n\n"
                "**사용 예시**\n"
                "```\n"
                "Tekton 도입 여부를 결정해줘\n"
                "Harbor가 필요한지 분석해줘\n"
                "Prometheus를 설치해야 할까?\n"
                "```\n\n"
                "**결과물**\n"
                "✅ 도입 추천 또는 ❌ 도입 비추천 (이유 포함)\n"
                "🔄 대안 제시\n"
                "📌 구현 가이드 (도입하는 경우)\n\n"
                "궁금한 도구를 알려주세요!"
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
                            "planning": "도구 요구사항 분석",
                            "research": "클러스터 상태 분석",
                            "prompt_generator": "의사결정 보고서 생성"
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
                            "planning": "📋 도구 요구사항 분석 중...",
                            "research": "🔍 클러스터 상태 분석 중...",
                            "prompt_generator": "💡 의사결정 보고서 생성 중...",
                            "end": "✨ 분석 완료!"
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
        "orchestrator": "조율자 (Claude 4.5)",
        "planning": "요구사항 분석 (Claude 4.5)",
        "research": "클러스터 분석 (Groq)",
        "prompt_generator": "의사결정 (Claude 4.5)"
    }
    return rename_dict.get(orig_author, orig_author)

