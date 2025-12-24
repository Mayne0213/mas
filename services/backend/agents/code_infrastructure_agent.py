"""
Infrastructure Code Agent (Groq)
인프라/DevOps 코드 작성 전문 (Kubernetes, YAML, Docker)
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from tools.bash_tool import bash_tools
import os


# Groq 모델 초기화
groq_infrastructure = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.3  # 인프라는 더 정확하게
)


INFRASTRUCTURE_PROMPT = """당신은 Multi-Agent System의 **Infrastructure Code Agent**입니다.

## ⚠️ 실행 환경
- 컨테이너 내부: /app/
- 호스트 시스템 접근: execute_host 사용 (nsenter)
- 파일 생성 위치: /home/ubuntu/Projects/ (호스트)

## 역할
- Kubernetes Deployment, Service, Ingress YAML 작성
- Docker 컨테이너 설정
- CI/CD 파이프라인 구성
- 모니터링 및 로깅 설정
- ArgoCD, Tekton 등 GitOps 도구 활용

## 기술 스택
- Kubernetes: Deployment, Service, Ingress, ConfigMap, Secret
- Helm Charts
- Docker & Dockerfile
- ArgoCD, Tekton
- Prometheus, Grafana

## YAML 작성 가이드라인
1. **구조**:
   - 명확한 네임스페이스 분리
   - Label/Selector 일관성
   - Resource limits/requests 설정

2. **보안**:
   - Secret 사용
   - RBAC 설정
   - Network Policy

3. **모니터링**:
   - Liveness/Readiness Probe
   - Prometheus ServiceMonitor
   - Logging 설정

## 도구 사용 가이드:

### execute_host (호스트 작업용) ⭐ 주로 사용:
nsenter를 통해 호스트에 직접 접근합니다.
Projects 폴더는 /home/ubuntu/Projects/ 에 있습니다.
- YAML 파일 생성: execute_host("cat > /home/ubuntu/Projects/cluster-infrastructure/apps/myapp/deployment.yaml << 'EOF'\\nYAML내용\\nEOF")
- kubectl apply: execute_host("kubectl apply -f /home/ubuntu/Projects/cluster-infrastructure/apps/myapp/", use_sudo=True)
- Git 커밋: execute_host("cd /home/ubuntu/Projects/cluster-infrastructure && git add . && git commit -m 'Add myapp'")

### execute_bash (컨테이너 내부용):
- 간단한 테스트나 검증에만 사용

## 출력 형식
생성한 YAML 파일 목록과 배포 방법을 설명하세요.
"""


def infrastructure_code_node(state: AgentState) -> AgentState:
    """
    Infrastructure Code 노드: 인프라 코드 작성
    """
    messages = state["messages"]
    task_plan = state.get("task_plan", {})
    research_data = state.get("research_data", {})

    # Groq에 bash 도구 바인딩
    groq_with_tools = groq_infrastructure.bind_tools(bash_tools)

    # 코드 작성 요청 구성
    code_request = f"""
작업 계획: {task_plan.get('summary', '')}
수집된 정보: {research_data.get('summary', '')}

다음 인프라 코드/YAML을 작성해주세요.
"""

    # Groq 호출
    response = groq_with_tools.invoke([
        SystemMessage(content=INFRASTRUCTURE_PROMPT),
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
            response = groq_infrastructure.invoke([
                SystemMessage(content=INFRASTRUCTURE_PROMPT),
                HumanMessage(content=code_request),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}\n\n작업 결과를 요약해주세요.")
            ])

    content = response.content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    # 상태 업데이트
    state["code_outputs"]["infrastructure"] = content
    state["messages"].append({
        "role": "infrastructure_engineer",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state
