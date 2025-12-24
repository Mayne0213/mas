"""
Research Agent (Claude)
정보 수집 및 문서/코드베이스 검색
JSON 기반 명령어 생성 방식으로 재작성
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json
import re


# Claude 4.5 모델 초기화
claude_research = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0.3
)



RESEARCH_PROMPT = """Research Agent: Analyze cluster or retrieve information.

## Two Modes

### Mode 1: Information Query (정보 조회)
User wants specific information (password, status, list, etc.)
- Execute the requested kubectl command
- Return the result directly
- No analysis needed

### Mode 2: Deployment Analysis (배포 분석)
User wants deployment decision
- Analyze cluster state comprehensively
- Collect version, tools, resources
- Provide structured findings

## Request commands in JSON:
{"commands": [{"tool": "execute_host", "command": "kubectl get nodes", "use_sudo": true}]}

Rules:
- Request 1-2 commands at a time
- Use execute_host for kubectl commands (with use_sudo: true)
- Output ONLY JSON when requesting commands

## Final report format

### For Information Query:
{
  "summary": "정보 조회 완료",
  "result": "actual command result",
  "findings": [{"category": "조회 결과", "data": "..."}]
}

### For Deployment Analysis:
{
  "summary": "클러스터 상태 요약",
  "cluster_info": {
    "k8s_version": "v1.x.x",
    "nodes": "3 nodes",
    "existing_tools": ["ArgoCD", "Gitea"]
  },
  "findings": [{"category": "...", "data": "..."}]
}

Choose the appropriate format based on the user's request.
"""


def research_node(state: AgentState) -> AgentState:
    """
    Research 노드: 정보 수집 (JSON 기반 명령어 방식)
    """
    messages = state["messages"]
    request_type = state.get("request_type", "deployment_decision")
    task_plan = state.get("task_plan") or {}
    research_needed = task_plan.get("research_needed", []) if isinstance(task_plan, dict) else []

    # 사용자 원래 요청 찾기
    user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    # 연구 요청 구성
    if request_type == "information_query":
        # 정보 조회 모드: 사용자 요청을 그대로 전달
        research_request = f"사용자가 다음 정보를 요청했습니다:\n\n{user_message}\n\n해당 정보를 kubectl 명령어로 조회하여 결과를 반환해주세요."
    elif research_needed:
        # 배포 결정 모드: Planning의 지시 따름
        research_request = f"다음 정보를 수집해주세요:\n" + "\n".join(f"- {item}" for item in research_needed)
    else:
        # 기본 모드
        if user_message:
            research_request = f"사용자 요청: {user_message}\n\n위 요청에 필요한 정보를 수집하고 분석해주세요."
        else:
            research_request = "현재 시스템 상태를 분석하고 필요한 정보를 수집해주세요."
    
    # 대화 히스토리 (도구 실행 결과 포함)
    conversation = [
        SystemMessage(content=RESEARCH_PROMPT),
        HumanMessage(content=research_request)
    ]
    
    tool_outputs = []
    max_iterations = 2
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"Research Agent - Iteration {iteration}/{max_iterations}")
        print(f"{'='*80}")
        
        # Claude 호출
        response = claude_research.invoke(conversation)
        response_text = response.content
        
        print(f"Response: {response_text[:500]}...")
        print(f"\n📝 Full Response:\n{response_text}\n")  # 디버깅용 전체 응답 출력

        # JSON 명령어 추출 시도
        commands_executed = False

        # 방법 1: ```json ... ``` 블록에서 추출
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if not json_match:
            # 방법 2: 단순 {...} 블록 추출
            json_match = re.search(r'(\{[^{}]*"commands"[^{}]*\[.*?\][^{}]*\})', response_text, re.DOTALL)
        
        if json_match:
            try:
                commands_data = json.loads(json_match.group(1))
                
                # commands가 있으면 실행
                if "commands" in commands_data and commands_data["commands"]:
                    commands_executed = True
                    results = []
                    
                    for cmd_spec in commands_data["commands"][:2]:  # 최대 2개까지만 (토큰 절약)
                        tool_name = cmd_spec.get("tool", "execute_bash")
                        command = cmd_spec.get("command", "")
                        use_sudo = cmd_spec.get("use_sudo", False)
                        
                        if not command:
                            continue
                        
                        print(f"\n🔧 Executing: {tool_name}('{command[:80]}...')")
                        
                        # 도구 실행
                        try:
                            from tools.bash_tool import execute_bash, execute_host
                            
                            if tool_name == "execute_host":
                                result = execute_host.invoke({"command": command, "use_sudo": use_sudo})
                            else:
                                result = execute_bash.invoke({"command": command})
                            
                            results.append(f"Command: {command}\nResult: {result}")
                            print(f"✅ Success")
                            
                        except Exception as e:
                            error_msg = f"❌ Error: {str(e)}"
                            results.append(f"Command: {command}\nResult: {error_msg}")
                            print(error_msg)
                    
                    # 결과를 대화에 추가 (최신 것만 유지)
                    results_text = "\n\n".join(results)
                    tool_outputs.append(results_text)

                    # 요청 유형에 따라 다른 지시
                    if request_type == "information_query":
                        # 정보 조회: 바로 최종 리포트 작성 지시
                        next_instruction = f"명령어 실행 결과:\n\n{results_text}\n\n**이제 위 결과를 바탕으로 최종 리포트를 JSON 형식으로 작성하세요. 추가 명령어 없이 바로 리포트를 제출하세요.**\n\n형식:\n{{\n  \"summary\": \"정보 조회 완료\",\n  \"result\": \"사용자 질문에 대한 답변\",\n  \"findings\": [{{\"category\": \"조회 결과\", \"data\": \"...\"}}]\n}}"
                    else:
                        # 배포 분석: 선택권 제공
                        next_instruction = f"명령어 실행 결과:\n\n{results_text}\n\n계속 정보가 필요하면 추가 명령어를 요청하고, 충분한 정보를 수집했으면 최종 리포트를 JSON으로 제공해주세요."

                    # 전체 히스토리 대신 시스템 프롬프트 + 초기 요청 + 최신 결과만 유지
                    conversation = [
                        SystemMessage(content=RESEARCH_PROMPT),
                        HumanMessage(content=research_request),
                        HumanMessage(content=next_instruction)
                    ]

                    continue  # 다음 반복으로
                    
                # 최종 리포트인 경우
                elif "summary" in commands_data and "findings" in commands_data:
                    print("\n✅ 최종 리포트 수신")

                    # 요청 유형에 따라 다른 포맷
                    if request_type == "information_query":
                        # 정보 조회: 결과만 간단히 표시
                        result = commands_data.get("result", "")
                        findings = commands_data.get("findings", [])

                        summary_parts = ["✅ 조회 완료\n"]

                        # 조회 결과
                        if result:
                            summary_parts.append(f"**결과:**\n```\n{result}\n```")
                        elif findings:
                            for finding in findings[:3]:
                                data = finding.get("data", "")
                                if data:
                                    summary_parts.append(f"{data}")

                        final_content = "\n".join(summary_parts)

                        # 정보 조회는 바로 종료
                        state["current_agent"] = "end"

                    else:
                        # 배포 분석: 간단한 상태만 표시 (Decision agent가 상세 결과 표시)
                        final_content = "✅ 분석 완료"

                        # 배포 분석은 orchestrator로 돌아감 (decision으로 이동)
                        state["current_agent"] = "orchestrator"

                    state["research_data"] = commands_data
                    state["messages"].append({
                        "role": "research",
                        "content": final_content
                    })
                    return state
                    
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}")
        
        # 명령어도 없고 최종 리포트도 아니면 종료
        if not commands_executed:
            print("\n✅ 명령어 요청 없음, Claude 응답을 그대로 사용")

            # 요청 유형에 따라 다른 출력
            if request_type == "information_query":
                # 정보 조회: Claude 응답을 그대로 표시
                content = f"✅ 조회 완료\n\n{response_text}"
                state["current_agent"] = "end"
            else:
                # 배포 분석: 간단한 메시지만 (Decision agent가 상세 결과 표시)
                content = "✅ 분석 완료"
                state["current_agent"] = "orchestrator"

            state["research_data"] = {
                "summary": "정보 수집 완료",
                "findings": [{"category": "분석", "data": response_text}],
                "recommendations": []
            }
            state["messages"].append({
                "role": "research",
                "content": content
            })
            return state
    
    # 최대 반복 도달
    print(f"\n⚠️ 최대 반복 횟수 도달 ({max_iterations})")

    # 요청 유형에 따라 다른 출력
    if request_type == "information_query":
        # 정보 조회: 수집된 정보를 바탕으로 사용자 친화적인 답변 생성
        if tool_outputs:
            outputs_text = "\n\n".join(tool_outputs)

            # Claude에게 결과 해석 요청
            print("\n📝 결과 해석 요청 중...")
            interpretation_prompt = f"""수집된 정보를 바탕으로 사용자 질문에 답변해주세요.

**사용자 질문:** {user_message}

**수집된 정보:**
{outputs_text}

위 정보를 바탕으로:
1. 사용자 질문에 직접적으로 답변
2. 한국어로 간결하게 작성
3. 핵심 정보만 포함
4. 기술적 세부사항은 필요시에만 포함

답변:"""

            interpretation_response = claude_research.invoke([
                HumanMessage(content=interpretation_prompt)
            ])

            content = f"✅ 조회 완료\n\n{interpretation_response.content}"

            state["research_data"] = {
                "summary": "정보 수집 완료",
                "findings": [{"category": "클러스터 정보", "data": outputs_text}],
                "recommendations": []
            }
        else:
            content = "✅ 조회 완료\n\n⚠️ 충분한 정보를 수집하지 못했습니다."
            state["research_data"] = {
                "summary": "정보 수집 불완전",
                "findings": [{"category": "경고", "data": "추가 정보 필요"}],
                "recommendations": []
            }
        state["current_agent"] = "end"
    else:
        # 배포 분석: 간단한 메시지만 (Decision agent가 상세 결과 표시)
        content = "✅ 분석 완료"
        if tool_outputs:
            outputs_text = "\n\n".join(tool_outputs)
            state["research_data"] = {
                "summary": "정보 수집 완료",
                "findings": [{"category": "클러스터 정보", "data": outputs_text}],
                "recommendations": []
            }
        else:
            state["research_data"] = {
                "summary": "정보 수집 불완전",
                "findings": [{"category": "경고", "data": "추가 정보 필요"}],
                "recommendations": []
            }
        state["current_agent"] = "orchestrator"

    state["messages"].append({
        "role": "research",
        "content": content
    })

    return state
