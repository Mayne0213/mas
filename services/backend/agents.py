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


class AgentState(TypedDict):
    """에이전트 간 공유되는 상태"""
    messages: list
    current_agent: str
    task_type: str
    result: dict


# ===== MCP Tools =====

# === 1. Kubernetes MCP Tools ===
@tool
def k8s_get_nodes() -> str:
    """
    Get Kubernetes cluster nodes information including status, roles, CPU and memory.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            nodes = json.loads(result.stdout)
            info = []
            for node in nodes.get("items", []):
                name = node["metadata"]["name"]
                labels = node["metadata"].get("labels", {})
                roles = [k.split("/")[1] for k in labels if "node-role.kubernetes.io" in k]
                role_str = ",".join(roles) if roles else "worker"
                
                status = "Unknown"
                for cond in node["status"]["conditions"]:
                    if cond["type"] == "Ready":
                        status = "Ready" if cond["status"] == "True" else "NotReady"
                
                capacity = node["status"]["capacity"]
                cpu = capacity.get("cpu", "?")
                mem = capacity.get("memory", "?")
                
                info.append(f"• {name} [{role_str}]: {status} | CPU: {cpu}, Memory: {mem}")
            
            return f"📦 Kubernetes Nodes ({len(info)}):\n" + "\n".join(info)
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ kubectl error: {str(e)}"


@tool
def k8s_get_pods(namespace: str = "", label_selector: str = "") -> str:
    """
    Get Kubernetes pods with optional namespace and label filtering.
    Args:
        namespace: Filter by namespace (empty = all namespaces)
        label_selector: Filter by labels (e.g., "app=myapp")
    """
    try:
        cmd = ["kubectl", "get", "pods", "-o", "json"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        if label_selector:
            cmd.extend(["-l", label_selector])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            pods = json.loads(result.stdout)
            info = []
            for pod in pods.get("items", []):
                name = pod["metadata"]["name"]
                ns = pod["metadata"]["namespace"]
                phase = pod["status"]["phase"]
                restarts = sum(c.get("restartCount", 0) for c in pod["status"].get("containerStatuses", []))
                
                emoji = "✅" if phase == "Running" else "⚠️" if phase == "Pending" else "❌"
                info.append(f"{emoji} {ns}/{name}: {phase} (restarts: {restarts})")
            
            return f"🐳 Pods ({len(info)}):\n" + "\n".join(info[:50])  # Limit to 50
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ kubectl error: {str(e)}"


@tool
def k8s_get_deployments(namespace: str = "") -> str:
    """
    Get Kubernetes deployments with replica status.
    Args:
        namespace: Filter by namespace (empty = all namespaces)
    """
    try:
        cmd = ["kubectl", "get", "deployments", "-o", "json"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            deployments = json.loads(result.stdout)
            info = []
            for deploy in deployments.get("items", []):
                name = deploy["metadata"]["name"]
                ns = deploy["metadata"]["namespace"]
                desired = deploy["spec"].get("replicas", 0)
                ready = deploy["status"].get("readyReplicas", 0)
                
                emoji = "✅" if ready == desired else "⚠️"
                info.append(f"{emoji} {ns}/{name}: {ready}/{desired} ready")
            
            return f"📦 Deployments ({len(info)}):\n" + "\n".join(info[:30])
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ kubectl error: {str(e)}"


@tool
def k8s_get_pod_logs(namespace: str, pod_name: str, tail: int = 50) -> str:
    """
    Get logs from a Kubernetes pod.
    Args:
        namespace: Pod namespace
        pod_name: Pod name
        tail: Number of lines to show (default: 50)
    """
    try:
        result = subprocess.run(
            ["kubectl", "logs", "-n", namespace, pod_name, f"--tail={tail}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"📜 Logs for {namespace}/{pod_name}:\n```\n{result.stdout}\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ kubectl error: {str(e)}"


@tool
def k8s_describe_resource(resource_type: str, name: str, namespace: str = "default") -> str:
    """
    Describe a Kubernetes resource (pod, deployment, service, etc.).
    Args:
        resource_type: Type of resource (pod, deployment, service, etc.)
        name: Resource name
        namespace: Namespace (default: default)
    """
    try:
        result = subprocess.run(
            ["kubectl", "describe", resource_type, name, "-n", namespace],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # Return last 50 lines to keep it manageable
            lines = result.stdout.split("\n")
            return f"🔍 Describe {resource_type}/{name} in {namespace}:\n```\n" + "\n".join(lines[-50:]) + "\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ kubectl error: {str(e)}"


# === 2. PostgreSQL MCP Tools ===
@tool
def postgres_query(query: str, database: str = "postgres") -> str:
    """
    Execute a read-only PostgreSQL query.
    Args:
        query: SQL query to execute (SELECT only for safety)
        database: Database name (default: postgres)
    """
    if not query.strip().upper().startswith("SELECT"):
        return "❌ Only SELECT queries are allowed for safety"
    
    try:
        # Use kubectl exec to run psql in the PostgreSQL pod
        pg_password = os.getenv("POSTGRES_PASSWORD", "")
        cmd = [
            "kubectl", "exec", "-n", "postgresql", "postgresql-primary-0", "--",
            "env", f"PGPASSWORD={pg_password}",
            "psql", "-U", "bluemayne", "-d", database, "-c", query
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return f"📊 Query Result:\n```\n{result.stdout}\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ PostgreSQL error: {str(e)}"


@tool
def postgres_list_databases() -> str:
    """
    List all databases in PostgreSQL cluster.
    """
    try:
        pg_password = os.getenv("POSTGRES_PASSWORD", "")
        cmd = [
            "kubectl", "exec", "-n", "postgresql", "postgresql-primary-0", "--",
            "env", f"PGPASSWORD={pg_password}",
            "psql", "-U", "bluemayne", "-c", "\\l"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return f"🗄️ Databases:\n```\n{result.stdout}\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ PostgreSQL error: {str(e)}"


@tool
def postgres_table_info(database: str, table: str) -> str:
    """
    Get table schema information.
    Args:
        database: Database name
        table: Table name
    """
    query = f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position;"
    return postgres_query(query, database)


# === 3. Git MCP Tools ===
@tool
def git_list_repos() -> str:
    """
    List Git repositories in Gitea.
    """
    try:
        gitea_url = "https://gitea0213.kro.kr"
        # This would need Gitea API token - for now, just list known repos
        known_repos = ["mas", "jaejadle", "jovies", "portfolio", "todo", "cluster-infrastructure"]
        return f"📚 Git Repositories:\n" + "\n".join(f"• {gitea_url}/bluemayne/{repo}" for repo in known_repos)
    except Exception as e:
        return f"❌ Git error: {str(e)}"


@tool
def git_recent_commits(repo: str, limit: int = 10) -> str:
    """
    Get recent commits from a repository (requires local clone).
    Args:
        repo: Repository name
        limit: Number of commits to show (default: 10)
    """
    try:
        repo_path = f"/Users/bluemayne/Projects/{repo}"
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}"
        
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"-{limit}", "--oneline"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return f"📝 Recent commits in {repo}:\n```\n{result.stdout}\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ Git error: {str(e)}"


# === 4. Prometheus MCP Tools ===
@tool
def prometheus_query(query: str) -> str:
    """
    Execute a PromQL query against Prometheus.
    Args:
        query: PromQL query (e.g., "up", "node_cpu_seconds_total")
    """
    try:
        # Prometheus is accessible via kubectl port-forward or ingress
        # For now, use kubectl proxy approach
        result = subprocess.run(
            ["kubectl", "exec", "-n", "monitoring", "deployment/prometheus-kube-prometheus-operator", "--",
             "wget", "-qO-", f"http://localhost:9090/api/v1/query?query={query}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                output = []
                for r in results[:20]:  # Limit to 20 results
                    metric = r.get("metric", {})
                    value = r.get("value", [None, "N/A"])[1]
                    output.append(f"• {metric}: {value}")
                return f"📈 Prometheus Query Result:\n" + "\n".join(output)
            return f"❌ Query failed: {data}"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ Prometheus error: {str(e)}"


@tool
def prometheus_node_metrics() -> str:
    """
    Get node resource usage metrics from Prometheus.
    """
    query = "node_cpu_seconds_total"
    return prometheus_query(query)


# === 5. File System MCP Tools ===
@tool
def fs_read_file(file_path: str, max_lines: int = 100) -> str:
    """
    Read a file from the filesystem (with safety checks).
    Args:
        file_path: Path to file
        max_lines: Maximum lines to read (default: 100)
    """
    try:
        # Only allow reading from safe directories
        safe_dirs = ["/var/log", "/tmp", os.path.expanduser("~/Projects")]
        if not any(file_path.startswith(d) for d in safe_dirs):
            return f"❌ Access denied: {file_path} (not in safe directories)"
        
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"
        
        with open(file_path, "r") as f:
            lines = f.readlines()[:max_lines]
        
        return f"📄 File: {file_path}\n```\n{''.join(lines)}\n```"
    except Exception as e:
        return f"❌ File read error: {str(e)}"


@tool
def fs_list_directory(dir_path: str) -> str:
    """
    List contents of a directory.
    Args:
        dir_path: Directory path
    """
    try:
        if not os.path.exists(dir_path):
            return f"❌ Directory not found: {dir_path}"
        
        if not os.path.isdir(dir_path):
            return f"❌ Not a directory: {dir_path}"
        
        items = os.listdir(dir_path)
        dirs = [f"📁 {item}/" for item in items if os.path.isdir(os.path.join(dir_path, item))]
        files = [f"📄 {item}" for item in items if os.path.isfile(os.path.join(dir_path, item))]
        
        return f"📂 Directory: {dir_path}\n" + "\n".join(sorted(dirs) + sorted(files))
    except Exception as e:
        return f"❌ Directory list error: {str(e)}"


# === 6. Docker/Container Registry MCP Tools ===
@tool
def docker_list_images(registry: str = "gitea0213.kro.kr") -> str:
    """
    List Docker images in registry.
    Args:
        registry: Registry URL (default: gitea0213.kro.kr)
    """
    try:
        # List known images
        known_images = ["mas", "jaejadle", "jovies", "portfolio", "todo"]
        return f"🐳 Docker Images in {registry}:\n" + "\n".join(
            f"• {registry}/bluemayne/{img}:latest" for img in known_images
        )
    except Exception as e:
        return f"❌ Docker error: {str(e)}"


# MCP Tools Collection
mcp_tools = [
    # Kubernetes
    k8s_get_nodes,
    k8s_get_pods,
    k8s_get_deployments,
    k8s_get_pod_logs,
    k8s_describe_resource,
    # PostgreSQL
    postgres_query,
    postgres_list_databases,
    postgres_table_info,
    # Git
    git_list_repos,
    git_recent_commits,
    # Prometheus
    prometheus_query,
    prometheus_node_metrics,
    # File System
    fs_read_file,
    fs_list_directory,
    # Docker
    docker_list_images,
]


# ===== 1. Claude Code - Orchestrator =====
claude_orchestrator = ChatAnthropic(
    model="claude-sonnet-4-5",  # Latest Claude Sonnet 4.5 (Sep 2025)
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
).bind_tools(mcp_tools)  # Bind MCP tools to Claude

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

**사용 가능한 도구(Tools)**:
당신은 실제 서버 상태에 접근할 수 있는 다양한 도구를 사용할 수 있습니다:

1. **Kubernetes 도구**:
   - k8s_get_nodes(): 노드 상태 조회
   - k8s_get_pods(namespace, label_selector): Pod 목록 조회
   - k8s_get_deployments(namespace): Deployment 목록
   - k8s_get_pod_logs(namespace, pod_name, tail): Pod 로그 확인
   - k8s_describe_resource(resource_type, name, namespace): 리소스 상세 정보

2. **PostgreSQL 도구**:
   - postgres_query(query, database): SQL SELECT 쿼리 실행
   - postgres_list_databases(): 데이터베이스 목록
   - postgres_table_info(database, table): 테이블 스키마 정보

3. **Git 도구**:
   - git_list_repos(): 레포지토리 목록
   - git_recent_commits(repo, limit): 최근 커밋 조회

4. **Prometheus 도구**:
   - prometheus_query(query): PromQL 쿼리 실행
   - prometheus_node_metrics(): 노드 메트릭 조회

5. **파일 시스템 도구**:
   - fs_read_file(file_path, max_lines): 파일 읽기
   - fs_list_directory(dir_path): 디렉토리 목록

6. **Docker 도구**:
   - docker_list_images(registry): 레지스트리 이미지 목록

**사용 방법**:
- 사용자가 클러스터 상태, 로그, 데이터베이스 등을 물어보면 **반드시 도구를 사용**하여 실제 정보를 확인하세요
- 추측하지 말고, 도구를 통해 확인한 실제 데이터를 기반으로 답변하세요
- 여러 정보가 필요한 경우 여러 도구를 순차적으로 사용하세요

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
)

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
)

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
)

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
    if "backend" in content_lower or "api" in content_lower or "fastapi" in content_lower:
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
    
    state["messages"].append({
        "role": "backend_developer",
        "content": response.content
    })
    state["current_agent"] = "orchestrator"  # 결과를 오케스트레이터에게 반환
    
    return state


def frontend_node(state: AgentState) -> AgentState:
    """Groq #2 - 프론트엔드 개발"""
    messages = state["messages"]
    
    response = groq_frontend.invoke([
        SystemMessage(content=FRONTEND_PROMPT),
        HumanMessage(content=messages[-1]["content"])
    ])
    
    state["messages"].append({
        "role": "frontend_developer",
        "content": response.content
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
    
    state["messages"].append({
        "role": "sre_specialist",
        "content": response.content
    })
    state["current_agent"] = "orchestrator"
    
    return state


def router(state: AgentState) -> Literal["backend_developer", "frontend_developer", "sre_specialist", "end"]:
    """다음 에이전트 라우팅"""
    current = state.get("current_agent", "orchestrator")
    
    if current == "backend_developer":
        return "backend_developer"
    elif current == "frontend_developer":
        return "frontend_developer"
    elif current == "sre_specialist":
        return "sre_specialist"
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
    
    # 엣지 정의
    workflow.set_entry_point("orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        router,
        {
            "backend_developer": "backend_developer",
            "frontend_developer": "frontend_developer",
            "sre_specialist": "sre_specialist",
            "end": END
        }
    )
    
    # 각 에이전트는 작업 후 orchestrator로 복귀
    workflow.add_edge("backend_developer", "orchestrator")
    workflow.add_edge("frontend_developer", "orchestrator")
    workflow.add_edge("sre_specialist", "orchestrator")
    
    return workflow.compile()


# 그래프 인스턴스 생성
mas_graph = create_mas_graph()

