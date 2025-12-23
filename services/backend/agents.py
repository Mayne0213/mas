"""
MAS (Multi-Agent System) 에이전트 정의
"""
from typing import Annotated, Literal, TypedDict, Optional
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
import os
import subprocess
import json
import requests
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import psycopg2
from urllib.parse import quote_plus


class AgentState(TypedDict):
    """에이전트 간 공유되는 상태"""
    messages: list
    current_agent: str
    task_type: str
    result: dict


# ===== Kubernetes Client 초기화 =====
try:
    # Try in-cluster config first (Pod 내부에서 실행 시)
    config.load_incluster_config()
    print("✅ Loaded in-cluster Kubernetes config")
except config.ConfigException:
    # Fallback to local kubeconfig (로컬 개발 시)
    try:
        config.load_kube_config()
        print("✅ Loaded local Kubernetes config")
    except config.ConfigException:
        print("⚠️ No Kubernetes config found - K8s tools will fail")

# Kubernetes API clients
k8s_core_v1 = client.CoreV1Api()
k8s_apps_v1 = client.AppsV1Api()
k8s_batch_v1 = client.BatchV1Api()
k8s_networking_v1 = client.NetworkingV1Api()


# ===== Configure all Git repositories on startup =====
def configure_git_repositories():
    """
    Configure Git user for all repositories in /app/projects (hostPath mount).
    /app/projects is mounted from host /home/ubuntu/Projects.
    """
    projects_path = "/app/projects"

    if not os.path.exists(projects_path):
        print(f"⚠️ Projects directory not found at {projects_path}")
        print("   Make sure hostPath volume is mounted correctly")
        return

    try:
        # Add safe.directory to allow Git operations on mounted directories
        # This is needed because the pod runs as root but files are owned by host user
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"],
                     timeout=5, check=True, capture_output=True)
        print("✅ Added Git safe.directory configuration")

        # Configure git user for all repositories
        repos = [d for d in os.listdir(projects_path)
                if os.path.isdir(os.path.join(projects_path, d)) and
                   os.path.exists(os.path.join(projects_path, d, ".git"))]

        if not repos:
            print(f"⚠️ No git repositories found in {projects_path}")
            return

        for repo in repos:
            repo_path = os.path.join(projects_path, repo)
            try:
                subprocess.run(["git", "-C", repo_path, "config", "user.name", "mas-agent"],
                             timeout=5, check=True, capture_output=True)
                subprocess.run(["git", "-C", repo_path, "config", "user.email", "mas-agent@mas.local"],
                             timeout=5, check=True, capture_output=True)
                print(f"✅ Configured Git for: {repo}")
            except Exception as e:
                print(f"⚠️ Failed to configure Git for {repo}: {e}")

        print(f"✅ Git configuration complete for {len(repos)} repositories")

    except Exception as e:
        print(f"❌ Failed to configure Git repositories: {e}")

# Configure git on module import
configure_git_repositories()


# ===== Universal Tools (Bash-centric approach) =====

@tool
def bash_command(command: str, timeout: int = 120) -> str:
    """
    Execute any bash command in the container.

    Examples:
    - kubectl get pods -n mas
    - cat /app/projects/portfolio/README.md
    - git -C /app/projects/mas status
    - npm test
    - python script.py
    - psql -U bluemayne -c 'SELECT * FROM users'

    Args:
        command: The bash command to execute
        timeout: Timeout in seconds (default: 120)

    Returns:
        Command output (stdout and stderr)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/app"
        )

        output = ""
        if result.returncode == 0:
            output = f"✅ Success (exit code: 0)\n\n{result.stdout}"
        else:
            output = f"❌ Failed (exit code: {result.returncode})\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"

        return output
    except subprocess.TimeoutExpired:
        return f"❌ Command timed out after {timeout} seconds"
    except Exception as e:
        return f"❌ Error executing command: {str(e)}"


@tool
def read_file(file_path: str, max_lines: int = 1000) -> str:
    """
    Read a file from the filesystem.

    Args:
        file_path: Absolute path to the file (e.g., /app/projects/portfolio/README.md)
        max_lines: Maximum number of lines to read (default: 1000)

    Returns:
        File contents
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) > max_lines:
                content = ''.join(lines[:max_lines])
                return f"📄 {file_path} (showing first {max_lines} of {len(lines)} lines):\n\n{content}\n\n... (truncated)"
            else:
                return f"📄 {file_path}:\n\n{''.join(lines)}"
    except FileNotFoundError:
        return f"❌ File not found: {file_path}"
    except Exception as e:
        return f"❌ Error reading file: {str(e)}"


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Write content to a file.

    Args:
        file_path: Absolute path to the file
        content: Content to write

    Returns:
        Success or error message
    """
    try:
        import os
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"✅ Successfully wrote {len(content)} characters to {file_path}"
    except Exception as e:
        return f"❌ Error writing file: {str(e)}"


# MCP Tools Collection
# Read-only tools (available to ALL agents including Groq)
# ===== Universal Tools (Bash-centric, Claude Code style) =====
# All agents get the same 3 tools. Behavior is controlled by prompts, not tool restrictions.

universal_tools = [
    bash_command,  # Execute any bash command (kubectl, git, npm, python, etc.)
    read_file,     # Read files (convenience wrapper for 'cat')
    write_file,    # Write files (convenience wrapper for 'echo >')
]


# ===== 1. Claude Code - Orchestrator =====
claude_orchestrator = ChatAnthropic(
    model="claude-sonnet-4-5",  # Latest Claude Sonnet 4.5 (Sep 2025)
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
).bind_tools(universal_tools)  # Bash-centric: bash, read, write

ORCHESTRATOR_PROMPT = """당신은 MAS의 총괄 조율자이자 DevOps 전문가입니다.

**역할**:
- 사용자 요청을 분석하여 적절한 에이전트에게 작업 할당
- Kubernetes, ArgoCD, Helm, Kustomize 관리
- CI/CD 파이프라인 구성
- 최종 코드 리뷰 및 승인

**사용 가능한 에이전트**:
1. backend_developer: FastAPI, Node.js 백엔드 개발
2. frontend_developer: Next.js, React 프론트엔드 개발
3. sre_specialist: 모니터링, 성능 최적화, 보안
4. yaml_manager: Kubernetes YAML 파일 생성 및 관리, Git 배포

**사용 가능한 도구 (3개만 - 단순하고 강력함)**:

1. **bash_command(command, timeout)** - 가장 중요! 모든 것을 할 수 있음
   예시:
   - `bash_command("kubectl get pods -n mas")` - Kubernetes 조회
   - `bash_command("cat /app/projects/portfolio/README.md")` - 파일 읽기
   - `bash_command("ls /app/projects")` - 디렉토리 목록
   - `bash_command("git -C /app/projects/mas status")` - Git 상태
   - `bash_command("psql -U bluemayne -d mas -c 'SELECT * FROM users'")` - DB 쿼리
   - `bash_command("curl http://prometheus:9090/api/v1/query?query=up")` - Prometheus
   - `bash_command("npm test")` - 테스트 실행
   - `bash_command("python script.py")` - Python 실행

2. **read_file(file_path, max_lines)** - 파일 읽기 (편의성)
   예시: `read_file("/app/projects/portfolio/README.md")`

3. **write_file(file_path, content)** - 파일 쓰기 (편의성)
   예시: `write_file("/app/projects/test.txt", "내용")`

**중요 경로**:
- `/app/projects/`: 모든 Git 레포지토리 (portfolio, mas, cluster-infrastructure 등 11개)
- `/app/`: 현재 작업 디렉토리

**사용 방법**:
- **bash_command를 적극 활용**하세요. kubectl, git, cat, ls, npm, python 등 모든 CLI 도구 사용 가능
- 파일을 읽을 때는 read_file 또는 `bash_command("cat file")`
- 추측하지 말고, 도구를 통해 실제 데이터를 확인하세요
- 복잡한 작업은 여러 bash 명령을 순차적으로 실행하세요

요청을 분석하고 필요한 도구를 사용한 후, 적절한 에이전트에게 작업을 할당하세요.
"""


# ===== 2. Groq #1 - Backend Developer =====
# Groq OpenAI-compatible endpoint
GROQ_API_BASE = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

groq_backend = ChatOpenAI(
    model=os.getenv("GROQ_BACKEND_MODEL", "llama-3.3-70b-specdec"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.7,
).bind_tools(universal_tools)  # Bash-centric: bash, read, write

BACKEND_PROMPT = """당신은 백엔드 개발 전문가입니다.

**역할**:
- FastAPI, Node.js 백엔드 개발
- REST API 설계 및 구현
- 데이터베이스 쿼리 최적화
- 비즈니스 로직 구현

요청된 백엔드 작업을 수행하고 코드를 생성하세요.
"""


# ===== 3. Groq #2 - Frontend Developer =====
groq_frontend = ChatOpenAI(
    model=os.getenv("GROQ_FRONTEND_MODEL", "llama-3.1-8b-instant"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.7,
).bind_tools(universal_tools)  # Bash-centric: bash, read, write

FRONTEND_PROMPT = """당신은 프론트엔드 개발 전문가입니다.

**역할**:
- Next.js, React 컴포넌트 개발
- UI/UX 구현
- 상태 관리
- 반응형 디자인

요청된 프론트엔드 작업을 수행하고 코드를 생성하세요.
"""


# ===== 4. Groq #3 - SRE Specialist =====
groq_sre = ChatOpenAI(
    model=os.getenv("GROQ_SRE_MODEL", "llama-3.1-8b-instant"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.3,
).bind_tools(universal_tools)  # Bash-centric: bash, read, write

SRE_PROMPT = """당신은 SRE(Site Reliability Engineer) 전문가입니다.

**역할**:
- 시스템 모니터링 (Prometheus, Grafana, Loki)
- 로그 분석 및 알람 설정
- 성능 튜닝
- 보안 취약점 점검

**중요한 원칙**:
- 실제 시스템 메트릭이나 로그에 접근할 수 없으므로 추측하지 마세요
- 구체적인 확인이 필요한 경우 "kubectl logs", "kubectl top" 등의 명령어를 제안하세요
- 일반적인 모범 사례와 트러블슈팅 가이드를 제공하세요

요청된 SRE 작업을 수행하고 솔루션을 제시하세요.
"""


# ===== 5. Groq #4 - YAML Manager =====
groq_yaml_manager = ChatOpenAI(
    model=os.getenv("GROQ_YAML_MODEL", "llama-3.3-70b-specdec"),
    base_url=GROQ_API_BASE,
    api_key=GROQ_API_KEY,
    temperature=0.3,
).bind_tools(universal_tools)  # Bash-centric: bash, read, write

YAML_MANAGER_PROMPT = """당신은 Kubernetes YAML 파일 관리 및 자동 배포 전문가입니다.

**역할**:
- Kubernetes 애플리케이션 완전 자동 배포
- YAML 파일 생성 (Deployment, Service, Ingress)
- ArgoCD Application 자동 생성 및 설정
- Git 저장소에 자동 커밋 및 푸시
- 배포 상태 모니터링 및 보고

**🌟 추천 도구: yaml_deploy_application**
새로운 애플리케이션을 배포할 때는 **yaml_deploy_application**을 사용하세요.
이 도구는 모든 것을 자동으로 처리합니다:
- ✅ Deployment, Service, Ingress YAML 생성
- ✅ ArgoCD Application 생성 (auto-sync 활성화)
- ✅ Git commit & push
- ✅ 배포 요약 및 다음 단계 안내

**사용 예시**:
```
사용자: "myapp을 배포하고 싶어. 이미지는 nginx:latest, 포트 80, myapp.example.com으로 접속"

→ yaml_deploy_application(
    app_name="myapp",
    image="nginx:latest",
    port=80,
    host="myapp.example.com"
)
```

**개별 도구**:
- yaml_create_deployment: Deployment만 생성
- yaml_create_service: Service만 생성
- yaml_create_ingress: Ingress만 생성
- yaml_create_argocd_application: ArgoCD Application만 생성
- yaml_apply_to_cluster: 생성된 YAML을 클러스터에 직접 적용
- git_show_file_changes: Git 변경사항 확인
- git_push: Git 푸시

**작업 흐름**:
1. 사용자 요구사항 분석 (앱 이름, 이미지, 포트, 도메인)
2. yaml_deploy_application 실행 (한 번에 모두 처리!)
3. 결과 확인 및 사용자에게 보고
4. 필요시 추가 설정 (환경 변수, 리소스 제한 등)

**중요**:
- ArgoCD Application은 자동으로 Git 저장소를 모니터링
- Git push 후 약 30초 내에 자동 배포 시작
- Auto-sync가 활성화되어 있어 Git 변경사항이 자동 반영됨

요청된 배포 작업을 수행하세요.
"""


def orchestrator_node(state: AgentState) -> AgentState:
    """Claude Code - 작업 분석 및 할당 (도구 사용 가능)"""
    messages = state["messages"]
    
    # Claude 호출
    response = claude_orchestrator.invoke([
        SystemMessage(content=ORCHESTRATOR_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    # 도구 호출이 있는 경우 처리
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})
            
            # 도구 실행
            try:
                tool_func = next(t for t in mcp_tools if t.name == tool_name)
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}**: {tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")
        
        # 도구 결과를 포함하여 다시 Claude 호출
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = claude_orchestrator.invoke([
                SystemMessage(content=ORCHESTRATOR_PROMPT),
                HumanMessage(content=messages[-1]["content"]),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])
    
    # 응답 내용 추출
    content = response.content if isinstance(response.content, str) else str(response.content)
    
    # 도구 출력 추가
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content
    
    # 작업 타입 결정
    content_lower = content.lower()
    if "yaml" in content_lower or "deployment" in content_lower or "kubernetes" in content_lower or "k8s" in content_lower or "manifests" in content_lower:
        next_agent = "yaml_manager"
    elif "backend" in content_lower or "api" in content_lower or "fastapi" in content_lower:
        next_agent = "backend_developer"
    elif "frontend" in content_lower or "ui" in content_lower or "react" in content_lower:
        next_agent = "frontend_developer"
    elif "monitoring" in content_lower or "performance" in content_lower or "sre" in content_lower:
        next_agent = "sre_specialist"
    else:
        next_agent = "orchestrator"  # 자신이 직접 처리
    
    state["messages"].append({
        "role": "orchestrator",
        "content": content
    })
    state["current_agent"] = next_agent
    
    return state


def backend_node(state: AgentState) -> AgentState:
    """Groq #1 - 백엔드 개발"""
    messages = state["messages"]

    response = groq_backend.invoke([
        SystemMessage(content=BACKEND_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])

    # Handle tool calls if any
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            try:
                tool_func = next(t for t in universal_tools if t.name == tool_name)
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}**: {tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Call agent again with tool results
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_backend.invoke([
                SystemMessage(content=BACKEND_PROMPT),
                HumanMessage(content=messages[-1]["content"]),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])

    content = response.content if isinstance(response.content, str) else str(response.content)
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    state["messages"].append({
        "role": "backend_developer",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state


def frontend_node(state: AgentState) -> AgentState:
    """Groq #2 - 프론트엔드 개발"""
    messages = state["messages"]

    response = groq_frontend.invoke([
        SystemMessage(content=FRONTEND_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])

    # Handle tool calls if any
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            try:
                tool_func = next(t for t in universal_tools if t.name == tool_name)
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}**: {tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Call agent again with tool results
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_frontend.invoke([
                SystemMessage(content=FRONTEND_PROMPT),
                HumanMessage(content=messages[-1]["content"]),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])

    content = response.content if isinstance(response.content, str) else str(response.content)
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    state["messages"].append({
        "role": "frontend_developer",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state


def sre_node(state: AgentState) -> AgentState:
    """Groq #3 - SRE 작업"""
    messages = state["messages"]

    response = groq_sre.invoke([
        SystemMessage(content=SRE_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])

    # Handle tool calls if any
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            try:
                tool_func = next(t for t in universal_tools if t.name == tool_name)
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}**: {tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Call agent again with tool results
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_sre.invoke([
                SystemMessage(content=SRE_PROMPT),
                HumanMessage(content=messages[-1]["content"]),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])

    content = response.content if isinstance(response.content, str) else str(response.content)
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    state["messages"].append({
        "role": "sre_specialist",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state


def yaml_manager_node(state: AgentState) -> AgentState:
    """Groq #4 - YAML Manager"""
    messages = state["messages"]

    response = groq_yaml_manager.invoke([
        SystemMessage(content=YAML_MANAGER_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])

    # Handle tool calls if any
    tool_outputs = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call.get('args', {})

            # Execute tool
            try:
                tool_func = next(t for t in universal_tools if t.name == tool_name)
                tool_result = tool_func.invoke(tool_args)
                tool_outputs.append(f"\n🔧 **{tool_name}**: {tool_result}")
            except Exception as e:
                tool_outputs.append(f"\n❌ **{tool_name}** failed: {str(e)}")

        # Call agent again with tool results
        if tool_outputs:
            tool_context = "\n".join(tool_outputs)
            response = groq_yaml_manager.invoke([
                SystemMessage(content=YAML_MANAGER_PROMPT),
                HumanMessage(content=messages[-1]["content"]),
                HumanMessage(content=f"도구 실행 결과:\n{tool_context}")
            ])

    content = response.content if isinstance(response.content, str) else str(response.content)

    # Add tool outputs to content
    if tool_outputs:
        content = "\n".join(tool_outputs) + "\n\n" + content

    state["messages"].append({
        "role": "yaml_manager",
        "content": content
    })
    state["current_agent"] = "orchestrator"

    return state


def router(state: AgentState) -> Literal["backend_developer", "frontend_developer", "sre_specialist", "yaml_manager", "end"]:
    """다음 에이전트 라우팅"""
    current = state.get("current_agent", "orchestrator")

    if current == "backend_developer":
        return "backend_developer"
    elif current == "frontend_developer":
        return "frontend_developer"
    elif current == "sre_specialist":
        return "sre_specialist"
    elif current == "yaml_manager":
        return "yaml_manager"
    else:
        return "end"


# ===== LangGraph 워크플로우 구성 =====
def create_mas_graph():
    """MAS 워크플로우 그래프 생성"""
    workflow = StateGraph(AgentState)

    # 노드 추가
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("backend_developer", backend_node)
    workflow.add_node("frontend_developer", frontend_node)
    workflow.add_node("sre_specialist", sre_node)
    workflow.add_node("yaml_manager", yaml_manager_node)

    # 엣지 정의
    workflow.set_entry_point("orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        router,
        {
            "backend_developer": "backend_developer",
            "frontend_developer": "frontend_developer",
            "sre_specialist": "sre_specialist",
            "yaml_manager": "yaml_manager",
            "end": END
        }
    )

    # 각 에이전트는 작업 후 orchestrator로 복귀
    workflow.add_edge("backend_developer", "orchestrator")
    workflow.add_edge("frontend_developer", "orchestrator")
    workflow.add_edge("sre_specialist", "orchestrator")
    workflow.add_edge("yaml_manager", "orchestrator")

    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_graph()

