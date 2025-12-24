"""
Research Agent (Groq)
정보 수집 및 문서/코드베이스 검색
JSON 기반 명령어 생성 방식으로 재작성
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
import os
import json
import re


# Groq 모델 초기화 (OpenAI 호환)
groq_research = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.3
)


RESEARCH_PROMPT = """Research Agent: Analyze Kubernetes cluster state.

Request commands in JSON:
{"commands": [{"tool": "execute_host", "command": "kubectl get nodes", "use_sudo": true}]}

Rules:
- Request 1-2 commands at a time
- Use execute_host for kubectl commands (with use_sudo: true)
- Focus on: version, existing tools, resources, nodes
- Output ONLY JSON when requesting commands

Final report format (Korean):
{
  "summary": "클러스터 상태 요약",
  "cluster_info": {
    "k8s_version": "v1.x.x",
    "nodes": "3 nodes (1 control-plane, 2 workers)",
    "existing_tools": ["ArgoCD", "Gitea", "Prometheus"]
  },
  "findings": [
    {"category": "기존 CI/CD", "data": "ArgoCD 운영 중"},
    {"category": "리소스", "data": "충분한 여유 있음"}
  ],
  "recommendation": {
    "deploy": true/false,
    "reasons": ["이유1", "이유2"],
    "alternatives": ["대안1", "대안2"]
  }
}

Keep findings concise and actionable. Focus on decision-making data.
"""


def research_node(state: AgentState) -> AgentState:
    """
    Research 노드: 정보 수집 (JSON 기반 명령어 방식)
    """
    messages = state["messages"]
    task_plan = state.get("task_plan") or {}
    research_needed = task_plan.get("research_needed", []) if isinstance(task_plan, dict) else []
    
    # 연구 요청 구성
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
        
        # Groq 호출
        response = groq_research.invoke(conversation)
        response_text = response.content
        
        print(f"Response: {response_text[:500]}...")
        
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
                    # 전체 히스토리 대신 시스템 프롬프트 + 초기 요청 + 최신 결과만 유지
                    conversation = [
                        SystemMessage(content=RESEARCH_PROMPT),
                        HumanMessage(content=research_request),
                        HumanMessage(content=f"명령어 실행 결과:\n\n{results_text}\n\n계속 정보가 필요하면 추가 명령어를 요청하고, 충분한 정보를 수집했으면 최종 리포트를 JSON으로 제공해주세요.")
                    ]
                    
                    continue  # 다음 반복으로
                    
                # 최종 리포트인 경우
                elif "summary" in commands_data and "findings" in commands_data:
                    print("\n✅ 최종 리포트 수신")
                    # 최종 리포트를 content에 포함
                    final_content = "\n".join(tool_outputs) + "\n\n## 최종 분석 결과\n\n" + json.dumps(commands_data, indent=2, ensure_ascii=False)
                    
                    state["research_data"] = commands_data
                    state["messages"].append({
                        "role": "research",
                        "content": final_content
                    })
                    state["current_agent"] = "orchestrator"
                    return state
                    
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}")
        
        # 명령어도 없고 최종 리포트도 아니면 종료
        if not commands_executed:
            print("\n✅ 명령어 요청 없음, 종료")
            # 텍스트 응답을 그대로 사용
            content = "\n".join(tool_outputs) + "\n\n" + response_text
            
            state["research_data"] = {
                "summary": "정보 수집 완료",
                "findings": [{"category": "raw", "data": response_text}],
                "recommendations": []
            }
            state["messages"].append({
                "role": "research",
                "content": content
            })
            state["current_agent"] = "orchestrator"
            return state
    
    # 최대 반복 도달
    print(f"\n⚠️ 최대 반복 횟수 도달 ({max_iterations})")
    content = "\n".join(tool_outputs) + "\n\n정보 수집을 완료했습니다."
    
    state["research_data"] = {
        "summary": "정보 수집 완료 (최대 반복 도달)",
        "findings": [{"category": "raw", "data": content}],
        "recommendations": []
    }
    state["messages"].append({
        "role": "research",
        "content": content
    })
    state["current_agent"] = "orchestrator"
    
    return state
