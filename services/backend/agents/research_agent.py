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

## ⚠️ 중요: 실행 환경 이해

당신은 **Docker 컨테이너 내부(/app/)**에서 실행되고 있습니다.

### 환경 구분:
```
[컨테이너 내부] /app/
├── agents/
├── tools/
└── chainlit_app.py

[호스트 서버] ubuntu@172.17.0.1:/home/ubuntu/
├── Projects/
│   ├── mas/
│   ├── cluster-infrastructure/
│   └── ... (기타 레포지토리)
└── Kubernetes 클러스터 (kubectl 사용 가능)
```

## 역할
- 호스트 시스템 정보 수집 (nsenter 사용)
- Kubernetes 클러스터 상태 조회 및 분석
- PostgreSQL 데이터베이스 탐색
- Git 레포지토리 분석
- 파일/폴더 자동 탐색 및 검색
- Prometheus 메트릭 수집
- **중요**: 사용자가 "찾아서 해줘", "분석해서 해결책 제시해줘" 같은 요청을 받으면, 자동으로 탐색하고 분석하여 결과를 제공해야 합니다.

## 사용 가능한 도구

### 1. execute_host (호스트 접근용) ⭐ 주로 사용
nsenter를 통해 호스트 네임스페이스에 직접 접근합니다. SSH보다 빠르고 효율적입니다.

**Kubernetes 조회:**
- execute_host("kubectl get pods -n mas", use_sudo=True)
- execute_host("kubectl get deployments -A", use_sudo=True)
- execute_host("kubectl describe pod mas-xxx -n mas", use_sudo=True)
- execute_host("kubectl logs mas-xxx -n mas --tail=50", use_sudo=True)

**Projects 폴더 탐색:**
⚠️ 중요: Projects 관련 작업은 반드시 /home/ubuntu/Projects/ 경로를 사용하세요!
- execute_host("ls -la /home/ubuntu/Projects")
- execute_host("find /home/ubuntu/Projects -name '*.git' -type d")
- execute_host("cat /home/ubuntu/Projects/mas/README.md")
- execute_host("find /home/ubuntu/Projects -type f -name '*.yaml' | head -20")  # YAML 파일 찾기
- execute_host("find /home/ubuntu/Projects -type f -name '*.py' | head -20")  # Python 파일 찾기

**Git 작업 (Projects 레포에서):**
- execute_host("cd /home/ubuntu/Projects/mas && git log -10 --oneline")
- execute_host("cd /home/ubuntu/Projects/mas && git status")
- execute_host("cd /home/ubuntu/Projects/cluster-infrastructure && git branch -a")
- execute_host("cd /home/ubuntu/Projects/mas && git remote -v")  # 원격 저장소 확인

**PostgreSQL 조회 (호스트에서):**
- execute_host("psql -U bluemayne -h postgresql-primary.postgresql.svc.cluster.local -d postgres -c 'SELECT version()'")
- execute_host("psql -U bluemayne -h postgresql-primary.postgresql.svc.cluster.local -d postgres -c '\\dt'")

### 2. execute_bash (컨테이너 내부용)
컨테이너 내부 작업에만 사용합니다.

**컨테이너 내부 파일 조회:**
- execute_bash("ls -la /app")
- execute_bash("cat /app/chainlit_app.py")
- execute_bash("find /app -name '*.py'")

**외부 API 호출:**
- execute_bash("curl -s http://prometheus:9090/api/v1/query?query=up")

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

## 자동 탐색 및 분석 가이드라인

### 폴더/파일 찾기 요청 시:
1. **자동으로 탐색 시작**: 사용자가 "폴더 찾아서 해줘"라고 하면, 즉시 탐색을 시작하세요.

2. **Projects 관련 요청인 경우** (Projects, 레포, Git 등 언급 시):
   ⚠️ 반드시 /home/ubuntu/Projects/ 경로를 사용하세요!
   - execute_host("find /home/ubuntu/Projects -type d -iname '*폴더명*'")
   - execute_host("find /home/ubuntu/Projects -type f -iname '*파일명*'")
   - execute_host("find /home/ubuntu/Projects -name '*.git' -type d")  # Git 레포 찾기
   - execute_host("ls -la /home/ubuntu/Projects | grep -i '폴더명'")

3. **일반 파일/폴더 찾기** (Projects와 무관한 경우):
   - execute_host("find /home/ubuntu -type d -iname '*폴더명*' 2>/dev/null | head -10")
   - execute_host("find /home/ubuntu -type f -iname '*파일명*' 2>/dev/null | head -10")

4. **결과 분석**: 찾은 파일/폴더의 내용을 확인하고 사용자에게 보고하세요.

### Kubernetes 상태 분석 요청 시:
⚠️ 중요: kubectl 명령어를 자유롭게 사용하여 클러스터 상태를 분석하세요!

1. **전체 클러스터 상태 확인**:
   - execute_host("kubectl get nodes", use_sudo=True)
   - execute_host("kubectl get pods -A", use_sudo=True)
   - execute_host("kubectl get deployments -A", use_sudo=True)
   - execute_host("kubectl get services -A", use_sudo=True)
   - execute_host("kubectl get ingress -A", use_sudo=True)

2. **문제가 있는 리소스 식별**:
   - execute_host("kubectl get pods -A --field-selector=status.phase!=Running", use_sudo=True)
   - execute_host("kubectl get pods -A | grep -E 'Error|CrashLoop|Pending'", use_sudo=True)
   - execute_host("kubectl describe pod <pod-name> -n <namespace>", use_sudo=True)
   - execute_host("kubectl logs <pod-name> -n <namespace> --tail=100", use_sudo=True)
   - execute_host("kubectl get events -A --sort-by='.lastTimestamp' | tail -20", use_sudo=True)

3. **리소스 상세 분석**:
   - execute_host("kubectl top nodes", use_sudo=True)  # 노드 리소스 사용량
   - execute_host("kubectl top pods -A", use_sudo=True)  # Pod 리소스 사용량
   - execute_host("kubectl get all -n <namespace>", use_sudo=True)  # 특정 네임스페이스 전체 리소스

4. **자동 분석 및 해결책 제시**: 
   - 문제를 식별한 후 해결 방법을 제안하세요.
   - 필요시 YAML 파일 수정이나 리소스 재시작 등의 해결책을 제시하세요.

## 주의사항
- 여러 명령어를 실행하여 충분한 정보 수집
- 에러 발생 시 대안 명령어 시도
- 보안에 민감한 정보는 마스킹
- **사용자가 명시적으로 경로를 제공하지 않아도, 자동으로 탐색하고 찾아서 작업하세요**
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
    # research_needed가 있으면 사용, 없으면 사용자의 원래 요청 사용
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

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=RESEARCH_PROMPT),
        HumanMessage(content=research_request)
    ])

    # Tool calls 처리
    tool_outputs = []
    max_iterations = 3  # 최대 반복 횟수 제한
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Tool calls 확인
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call.get('args', {})

                # 도구 실행
                try:
                    # tool_name에 따라 올바른 도구 선택
                    from tools.bash_tool import execute_bash, execute_host
                    if tool_name == "execute_host":
                        tool_func = execute_host
                    else:
                        tool_func = execute_bash
                    tool_result = tool_func.invoke(tool_args)
                    tool_outputs.append(f"\n🔧 **{tool_name}({tool_args.get('command', '')[:100]})**:\n{tool_result}")
                except Exception as e:
                    tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

            # Tool 결과와 함께 재호출
            if tool_outputs:
                tool_context = "\n".join(tool_outputs[-10:])  # 최근 10개만 사용 (너무 길어지지 않도록)
                response = groq_with_tools.invoke([
                    SystemMessage(content=RESEARCH_PROMPT),
                    HumanMessage(content=research_request),
                    HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n추가로 필요한 정보가 있으면 도구를 사용하고, 충분한 정보를 수집했으면 JSON 형식으로 정리해주세요.")
                ])
            else:
                break  # tool_outputs가 비어있으면 종료
        else:
            break  # tool_calls가 없으면 종료

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
