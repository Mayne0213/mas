"""
Research Agent (Groq)
정보 수집 및 문서/코드베이스 검색
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os
import json


# Groq 모델 초기화 (OpenAI 호환)
groq_research = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.3
)


RESEARCH_PROMPT = """당신은 Multi-Agent System의 **Research Agent**입니다.

## 역할
- Bash 명령어를 활용하여 필요한 정보 수집
- Kubernetes 클러스터 상태 조회
- PostgreSQL 데이터베이스 스키마/데이터 탐색
- Git 레포지토리 분석
- 파일 시스템 검색
- Prometheus 메트릭 수집

## 사용 가능한 도구
**execute_bash**: 모든 bash 명령어를 실행할 수 있습니다.

### 예시 명령어:

**Kubernetes 조회:**
- kubectl get pods -n mas
- kubectl get deployments -A
- kubectl describe pod <pod-name> -n <namespace>
- kubectl logs <pod-name> -n <namespace> --tail=50

**PostgreSQL 조회:**
- psql -U bluemayne -d postgres -c "\\dt"  # 테이블 목록
- psql -U bluemayne -d postgres -c "SELECT * FROM users LIMIT 10"
- psql -U bluemayne -d postgres -c "\\d users"  # 테이블 스키마

**Git 조회:**
- git log -10 --oneline
- git status
- git diff
- git branch -a

**파일 시스템:**
- ls -la /app/repos/
- cat /app/repos/cluster-infrastructure/README.md
- find /app/repos -name "*.yaml" -type f
- grep -r "keyword" /app/repos/

**Prometheus 메트릭:**
- curl -s "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query=up"
- curl -s "http://prometheus:9090/api/v1/query?query=node_cpu_seconds_total"

## 출력 형식 (JSON)
수집한 정보를 JSON 형식으로 정리하세요:
```json
{
  "summary": "수집한 정보 요약",
  "findings": [
    {"category": "카테고리", "data": "발견한 데이터"},
    {"category": "카테고리", "data": "발견한 데이터"}
  ],
  "recommendations": ["추천 사항 1", "추천 사항 2"]
}
```

## 주의사항
- 여러 명령어를 실행하여 충분한 정보 수집
- 에러 발생 시 대안 명령어 시도
- 보안에 민감한 정보는 마스킹
"""


def research_node(state: AgentState) -> AgentState:
    """
    Research 노드: 정보 수집
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_needed = task_plan.get("research_needed", [])

    # Groq에 bash 도구 바인딩
    groq_with_tools = groq_research.bind_tools(bash_tools)

    # 연구 요청 구성
    research_request = f"다음 정보를 수집해주세요:\n" + "\n".join(f"- {item}" for item in research_needed)

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=RESEARCH_PROMPT),
        HumanMessage(content=research_request)
    ])

    # Tool calls 처리
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            # 도구 실행
            try:
                tool_func = bash_tools[0]  # execute_bash
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}({tool_args.get('command', '')})**:\n{tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Tool 결과와 함께 재호출
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_research.invoke([
                SystemMessage(content=RESEARCH_PROMPT),
                HumanMessage(content=research_request),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n이제 JSON 형식으로 정리해주세요.")
            ])

    content = response.content

    # Tool outputs를 content에 포함
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # JSON 파싱 시도
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content

        research_data = json.loads(json_str)
    except Exception:
        research_data = {
            "summary": "정보 수집 완료",
            "findings": [{"category": "raw", "data": content}],
            "recommendations": []
        }

    # 상태 업데이트
    state["research_data"] = research_data
    state["messages"].append({
        "role": "research",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state
