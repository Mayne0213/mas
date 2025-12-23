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


# ===== Legacy MCP Tools (kept for backward compatibility, but not recommended) =====

# === 1. Kubernetes MCP Tools ===
@tool
def k8s_get_nodes() -> str:
    """
    Get Kubernetes cluster nodes information including status, roles, CPU and memory.
    """
    try:
        nodes = k8s_core_v1.list_node()
        info = []

        for node in nodes.items:
            name = node.metadata.name
            labels = node.metadata.labels or {}

            # Extract roles from labels
            roles = [k.split("/")[1] for k in labels if "node-role.kubernetes.io" in k]
            role_str = ",".join(roles) if roles else "worker"

            # Get node status
            status = "Unknown"
            for cond in node.status.conditions:
                if cond.type == "Ready":
                    status = "Ready" if cond.status == "True" else "NotReady"

            # Get capacity
            capacity = node.status.capacity
            cpu = capacity.get("cpu", "?")
            mem = capacity.get("memory", "?")

            info.append(f"• {name} [{role_str}]: {status} | CPU: {cpu}, Memory: {mem}")

        return f"📦 Kubernetes Nodes ({len(info)}):\n" + "\n".join(info)
    except ApiException as e:
        return f"❌ Kubernetes API error: {e.status} {e.reason}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def k8s_get_pods(namespace: str = "", label_selector: str = "") -> str:
    """
    Get Kubernetes pods with optional namespace and label filtering.
    Args:
        namespace: Filter by namespace (empty = all namespaces)
        label_selector: Filter by labels (e.g., "app=myapp")
    """
    try:
        # Get pods based on namespace filter
        if namespace:
            pods = k8s_core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector if label_selector else None
            )
        else:
            pods = k8s_core_v1.list_pod_for_all_namespaces(
                label_selector=label_selector if label_selector else None
            )

        info = []
        for pod in pods.items:
            name = pod.metadata.name
            ns = pod.metadata.namespace
            phase = pod.status.phase

            # Calculate total restarts
            restarts = 0
            if pod.status.container_statuses:
                restarts = sum(c.restart_count for c in pod.status.container_statuses)

            emoji = "✅" if phase == "Running" else "⚠️" if phase == "Pending" else "❌"
            info.append(f"{emoji} {ns}/{name}: {phase} (restarts: {restarts})")

        return f"🐳 Pods ({len(info)}):\n" + "\n".join(info[:50])  # Limit to 50
    except ApiException as e:
        return f"❌ Kubernetes API error: {e.status} {e.reason}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def k8s_get_deployments(namespace: str = "") -> str:
    """
    Get Kubernetes deployments with replica status.
    Args:
        namespace: Filter by namespace (empty = all namespaces)
    """
    try:
        # Get deployments based on namespace filter
        if namespace:
            deployments = k8s_apps_v1.list_namespaced_deployment(namespace=namespace)
        else:
            deployments = k8s_apps_v1.list_deployment_for_all_namespaces()

        info = []
        for deploy in deployments.items:
            name = deploy.metadata.name
            ns = deploy.metadata.namespace
            desired = deploy.spec.replicas or 0
            ready = deploy.status.ready_replicas or 0

            emoji = "✅" if ready == desired else "⚠️"
            info.append(f"{emoji} {ns}/{name}: {ready}/{desired} ready")

        return f"📦 Deployments ({len(info)}):\n" + "\n".join(info[:30])
    except ApiException as e:
        return f"❌ Kubernetes API error: {e.status} {e.reason}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


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
        logs = k8s_core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=tail
        )
        return f"📜 Logs for {namespace}/{pod_name}:\n```\n{logs}\n```"
    except ApiException as e:
        return f"❌ Kubernetes API error: {e.status} {e.reason}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


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
        resource_type = resource_type.lower()

        if resource_type in ["pod", "pods"]:
            resource = k8s_core_v1.read_namespaced_pod(name=name, namespace=namespace)
        elif resource_type in ["deployment", "deployments", "deploy"]:
            resource = k8s_apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        elif resource_type in ["service", "services", "svc"]:
            resource = k8s_core_v1.read_namespaced_service(name=name, namespace=namespace)
        elif resource_type in ["statefulset", "statefulsets", "sts"]:
            resource = k8s_apps_v1.read_namespaced_stateful_set(name=name, namespace=namespace)
        elif resource_type in ["daemonset", "daemonsets", "ds"]:
            resource = k8s_apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
        elif resource_type in ["ingress", "ingresses", "ing"]:
            resource = k8s_networking_v1.read_namespaced_ingress(name=name, namespace=namespace)
        else:
            return f"❌ Unsupported resource type: {resource_type}"

        # Format resource information
        result_lines = [
            f"Name: {resource.metadata.name}",
            f"Namespace: {resource.metadata.namespace}",
            f"Created: {resource.metadata.creation_timestamp}",
            f"Labels: {resource.metadata.labels}",
            f"Annotations: {resource.metadata.annotations}",
        ]

        # Add status if available
        if hasattr(resource, 'status') and resource.status:
            result_lines.append(f"Status: {resource.status}")

        output = "\n".join(str(line) for line in result_lines)
        return f"🔍 Describe {resource_type}/{name} in {namespace}:\n```\n{output}\n```"
    except ApiException as e:
        return f"❌ Kubernetes API error: {e.status} {e.reason}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === 2. PostgreSQL MCP Tools ===
def get_postgres_connection(database: str = "postgres"):
    """
    Create PostgreSQL connection using environment variables or k8s service.
    """
    # Try to connect via Kubernetes service (when running in cluster)
    pg_host = os.getenv("POSTGRES_HOST", "postgresql-primary.postgresql.svc.cluster.local")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_user = os.getenv("POSTGRES_USER", "bluemayne")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")

    return psycopg2.connect(
        host=pg_host,
        port=pg_port,
        user=pg_user,
        password=pg_password,
        database=database,
        connect_timeout=10
    )


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
        conn = get_postgres_connection(database)
        cursor = conn.cursor()
        cursor.execute(query)

        # Fetch results
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]

        # Format output
        result_lines = [" | ".join(colnames)]
        result_lines.append("-" * len(result_lines[0]))
        for row in rows[:100]:  # Limit to 100 rows
            result_lines.append(" | ".join(str(val) for val in row))

        cursor.close()
        conn.close()

        return f"📊 Query Result ({len(rows)} rows):\n```\n" + "\n".join(result_lines) + "\n```"
    except psycopg2.Error as e:
        return f"❌ PostgreSQL error: {e.pgcode} - {e.pgerror}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def postgres_list_databases() -> str:
    """
    List all databases in PostgreSQL cluster.
    """
    try:
        conn = get_postgres_connection("postgres")
        cursor = conn.cursor()
        cursor.execute("SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database WHERE datistemplate = false ORDER BY datname;")

        rows = cursor.fetchall()
        result_lines = ["Database | Size", "---------|-----"]
        for row in rows:
            result_lines.append(f"{row[0]} | {row[1]}")

        cursor.close()
        conn.close()

        return f"🗄️ Databases ({len(rows)}):\n```\n" + "\n".join(result_lines) + "\n```"
    except psycopg2.Error as e:
        return f"❌ PostgreSQL error: {e.pgcode} - {e.pgerror}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


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
        repo_path = f"/app/repos/{repo}"  # Container 내부 경로
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}. Use git_clone_repo first."
        
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"-{limit}", "--oneline"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return f"📝 Recent commits in {repo}:\n```\n{result.stdout}\n```"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ Git error: {str(e)}"


@tool
def git_clone_repo(repo_url: str, repo_name: str = "") -> str:
    """
    Clone a Git repository locally.
    Args:
        repo_url: Full repository URL (e.g., https://gitea0213.kro.kr/bluemayne/harbor.git)
        repo_name: Optional local directory name (default: extracted from URL)
    """
    try:
        if not repo_name:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
        
        repo_path = f"/app/repos/{repo_name}"
        os.makedirs("/app/repos", exist_ok=True)
        
        if os.path.exists(repo_path):
            return f"✅ Repository already exists: {repo_path}"
        
        # Use Gitea token if available
        token = os.getenv("GITEA_TOKEN", "")
        if token:
            # Inject token into URL
            if "gitea0213.kro.kr" in repo_url:
                repo_url = repo_url.replace("https://", f"https://{token}@")
        
        result = subprocess.run(
            ["git", "clone", repo_url, repo_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return f"✅ Cloned repository: {repo_name} to {repo_path}"
        return f"❌ Error: {result.stderr}"
    except Exception as e:
        return f"❌ Git clone error: {str(e)}"


@tool
def git_read_file(repo_name: str, file_path: str) -> str:
    """
    Read a file from a Git repository.
    Args:
        repo_name: Repository name (e.g., portfolio, mas, cluster-infrastructure)
        file_path: File path relative to repo root (e.g., README.md, src/index.js)
    """
    try:
        repo_path = f"/app/projects/{repo_name}"
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}"

        full_path = os.path.join(repo_path, file_path)
        if not os.path.exists(full_path):
            return f"❌ File not found: {file_path} in {repo_name}"

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return f"📄 {file_path} ({repo_name}):\n\n{content}"
    except Exception as e:
        return f"❌ Read file error: {str(e)}"


@tool
def git_create_file(repo_name: str, file_path: str, content: str, commit_message: str = "") -> str:
    """
    Create or update a file in a Git repository and commit it.
    Args:
        repo_name: Repository name (e.g., cluster-infrastructure, mas, etc.)
        file_path: File path relative to repo root
        content: File content
        commit_message: Commit message (default: "Add/Update {file_path}")
    """
    try:
        repo_path = f"/app/projects/{repo_name}"
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}. Available repos in /app/projects."
        
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w") as f:
            f.write(content)
        
        # Git add
        subprocess.run(["git", "-C", repo_path, "add", file_path], check=True, timeout=10)
        
        # Git commit
        if not commit_message:
            commit_message = f"Add/Update {file_path}"
        
        result = subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", commit_message],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            return f"✅ Created/Updated {file_path} and committed"
        return f"⚠️ File created but commit failed: {result.stderr}"
    except Exception as e:
        return f"❌ Git file error: {str(e)}"


@tool
def git_push(repo_name: str, branch: str = "main") -> str:
    """
    Push commits to remote repository.
    Args:
        repo_name: Repository name (e.g., cluster-infrastructure, mas, etc.)
        branch: Branch name (default: main)
    """
    try:
        repo_path = f"/app/projects/{repo_name}"
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}"
        
        # Configure git user if needed
        subprocess.run(["git", "-C", repo_path, "config", "user.name", "mas-agent"], timeout=5)
        subprocess.run(["git", "-C", repo_path, "config", "user.email", "mas-agent@mas.local"], timeout=5)
        
        result = subprocess.run(
            ["git", "-C", repo_path, "push", "origin", branch],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            return f"✅ Pushed to {branch} branch"
        return f"❌ Push failed: {result.stderr}"
    except Exception as e:
        return f"❌ Git push error: {str(e)}"


# === 4. Prometheus MCP Tools ===
@tool
def prometheus_query(query: str) -> str:
    """
    Execute a PromQL query against Prometheus.
    Args:
        query: PromQL query (e.g., "up", "node_cpu_seconds_total")
    """
    try:
        # Access Prometheus via Kubernetes service
        prometheus_url = os.getenv(
            "PROMETHEUS_URL",
            "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
        )

        # Make HTTP request
        response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={"query": query},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                output = []
                for r in results[:20]:  # Limit to 20 results
                    metric = r.get("metric", {})
                    value = r.get("value", [None, "N/A"])[1]
                    output.append(f"• {metric}: {value}")
                return f"📈 Prometheus Query Result ({len(results)} metrics):\n" + "\n".join(output)
            return f"❌ Query failed: {data}"
        return f"❌ HTTP Error: {response.status_code} - {response.text}"
    except requests.RequestException as e:
        return f"❌ Prometheus request error: {str(e)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


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
        # Allow reading from safe directories
        safe_dirs = ["/app/repos", "/var/log", "/tmp"]
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


# === 7. YAML Management MCP Tools ===
@tool
def yaml_create_deployment(
    app_name: str,
    image: str,
    replicas: int = 1,
    port: int = 8080,
    namespace: str = "default",
    env_vars: str = ""
) -> str:
    """
    Create Kubernetes Deployment YAML file.
    Args:
        app_name: Application name
        image: Container image (e.g., myregistry/myapp:v1.0)
        replicas: Number of replicas (default: 1)
        port: Container port (default: 8080)
        namespace: Namespace (default: default)
        env_vars: Environment variables as JSON string (e.g., '{"KEY": "value"}')
    """
    try:
        import yaml as yaml_lib

        # Parse env vars
        env_list = []
        if env_vars:
            env_dict = json.loads(env_vars)
            env_list = [{"name": k, "value": str(v)} for k, v in env_dict.items()]

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": app_name,
                "namespace": namespace,
                "labels": {"app": app_name}
            },
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": app_name}},
                "template": {
                    "metadata": {"labels": {"app": app_name}},
                    "spec": {
                        "containers": [{
                            "name": app_name,
                            "image": image,
                            "ports": [{"containerPort": port, "name": "http"}],
                            "env": env_list
                        }]
                    }
                }
            }
        }

        yaml_content = yaml_lib.dump(deployment, default_flow_style=False, sort_keys=False)

        # Save to file
        repo_path = "/app/repos/cluster-infrastructure"
        file_path = f"applications/{app_name}/deployment.yaml"
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w") as f:
            f.write(yaml_content)

        return f"✅ Created Deployment YAML:\n```yaml\n{yaml_content}\n```\n📁 Saved to: {file_path}"
    except Exception as e:
        return f"❌ Error creating deployment YAML: {str(e)}"


@tool
def yaml_create_service(
    app_name: str,
    port: int = 80,
    target_port: int = 8080,
    service_type: str = "ClusterIP",
    namespace: str = "default"
) -> str:
    """
    Create Kubernetes Service YAML file.
    Args:
        app_name: Application name
        port: Service port (default: 80)
        target_port: Target container port (default: 8080)
        service_type: Service type (ClusterIP, NodePort, LoadBalancer) (default: ClusterIP)
        namespace: Namespace (default: default)
    """
    try:
        import yaml as yaml_lib

        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": app_name,
                "namespace": namespace,
                "labels": {"app": app_name}
            },
            "spec": {
                "type": service_type,
                "selector": {"app": app_name},
                "ports": [{
                    "port": port,
                    "targetPort": target_port,
                    "name": "http"
                }]
            }
        }

        yaml_content = yaml_lib.dump(service, default_flow_style=False, sort_keys=False)

        # Save to file
        repo_path = "/app/repos/cluster-infrastructure"
        file_path = f"applications/{app_name}/service.yaml"
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w") as f:
            f.write(yaml_content)

        return f"✅ Created Service YAML:\n```yaml\n{yaml_content}\n```\n📁 Saved to: {file_path}"
    except Exception as e:
        return f"❌ Error creating service YAML: {str(e)}"


@tool
def yaml_create_ingress(
    app_name: str,
    host: str,
    service_port: int = 80,
    namespace: str = "default",
    tls_enabled: bool = True
) -> str:
    """
    Create Kubernetes Ingress YAML file.
    Args:
        app_name: Application name
        host: Ingress hostname (e.g., myapp.example.com)
        service_port: Service port (default: 80)
        namespace: Namespace (default: default)
        tls_enabled: Enable TLS/HTTPS (default: True)
    """
    try:
        import yaml as yaml_lib

        ingress = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{app_name}-ingress",
                "namespace": namespace,
                "labels": {"app": app_name},
                "annotations": {
                    "cert-manager.io/cluster-issuer": "letsencrypt-prod"
                }
            },
            "spec": {
                "ingressClassName": "nginx",
                "rules": [{
                    "host": host,
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": app_name,
                                    "port": {"number": service_port}
                                }
                            }
                        }]
                    }
                }]
            }
        }

        if tls_enabled:
            ingress["spec"]["tls"] = [{
                "hosts": [host],
                "secretName": f"{app_name}-tls"
            }]

        yaml_content = yaml_lib.dump(ingress, default_flow_style=False, sort_keys=False)

        # Save to file
        repo_path = "/app/repos/cluster-infrastructure"
        file_path = f"applications/{app_name}/ingress.yaml"
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w") as f:
            f.write(yaml_content)

        return f"✅ Created Ingress YAML:\n```yaml\n{yaml_content}\n```\n📁 Saved to: {file_path}"
    except Exception as e:
        return f"❌ Error creating ingress YAML: {str(e)}"


@tool
def yaml_apply_to_cluster(app_name: str, namespace: str = "default") -> str:
    """
    Apply YAML files to Kubernetes cluster.
    Args:
        app_name: Application name
        namespace: Namespace (default: default)
    """
    try:
        repo_path = "/app/repos/cluster-infrastructure"
        app_path = os.path.join(repo_path, f"applications/{app_name}")

        if not os.path.exists(app_path):
            return f"❌ Application directory not found: {app_path}"

        # Apply all YAML files in the directory
        results = []
        for yaml_file in os.listdir(app_path):
            if yaml_file.endswith(".yaml"):
                file_path = os.path.join(app_path, yaml_file)

                # Read YAML file
                with open(file_path, "r") as f:
                    yaml_content = f.read()

                # Parse YAML to get resource info
                import yaml as yaml_lib
                resource = yaml_lib.safe_load(yaml_content)
                kind = resource.get("kind", "Unknown")
                name = resource.get("metadata", {}).get("name", "unknown")

                # Apply using Python Kubernetes client
                try:
                    if kind == "Deployment":
                        k8s_apps_v1.create_namespaced_deployment(namespace=namespace, body=resource)
                    elif kind == "Service":
                        k8s_core_v1.create_namespaced_service(namespace=namespace, body=resource)
                    elif kind == "Ingress":
                        k8s_networking_v1.create_namespaced_ingress(namespace=namespace, body=resource)
                    else:
                        results.append(f"⚠️ {yaml_file}: Unsupported resource type {kind}")
                        continue

                    results.append(f"✅ {yaml_file}: {kind}/{name} created")
                except ApiException as e:
                    if e.status == 409:
                        results.append(f"ℹ️ {yaml_file}: {kind}/{name} already exists")
                    else:
                        results.append(f"❌ {yaml_file}: {e.reason}")

        return f"📦 Applied YAMLs for {app_name}:\n" + "\n".join(results)
    except Exception as e:
        return f"❌ Error applying YAMLs: {str(e)}"


@tool
def yaml_create_argocd_application(
    app_name: str,
    namespace: str = "default",
    repo_url: str = "https://gitea0213.kro.kr/bluemayne/cluster-infrastructure.git",
    path: str = "",
    auto_sync: bool = True
) -> str:
    """
    Create ArgoCD Application manifest for automatic deployment.
    Args:
        app_name: Application name
        namespace: Target namespace (default: default)
        repo_url: Git repository URL (default: cluster-infrastructure)
        path: Path to manifests in repo (default: applications/{app_name})
        auto_sync: Enable auto-sync (default: True)
    """
    try:
        import yaml as yaml_lib

        if not path:
            path = f"applications/{app_name}"

        application = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {
                "name": app_name,
                "namespace": "argocd",
                "finalizers": ["resources-finalizer.argocd.argoproj.io"]
            },
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": repo_url,
                    "targetRevision": "HEAD",
                    "path": path
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace
                },
                "syncPolicy": {
                    "automated": {
                        "prune": True,
                        "selfHeal": True
                    } if auto_sync else None,
                    "syncOptions": [
                        "CreateNamespace=true"
                    ]
                }
            }
        }

        yaml_content = yaml_lib.dump(application, default_flow_style=False, sort_keys=False)

        # Save to file
        repo_path = "/app/repos/cluster-infrastructure"
        file_path = f"argocd-applications/{app_name}.yaml"
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w") as f:
            f.write(yaml_content)

        return f"✅ Created ArgoCD Application:\n```yaml\n{yaml_content}\n```\n📁 Saved to: {file_path}"
    except Exception as e:
        return f"❌ Error creating ArgoCD Application: {str(e)}"


@tool
def yaml_deploy_application(
    app_name: str,
    image: str,
    port: int = 8080,
    replicas: int = 1,
    namespace: str = "default",
    host: str = "",
    env_vars: str = "",
    enable_ingress: bool = True,
    auto_sync_argocd: bool = True
) -> str:
    """
    Complete application deployment workflow:
    1. Create Deployment, Service, Ingress YAMLs
    2. Create ArgoCD Application
    3. Git commit and push
    4. Display changes

    Args:
        app_name: Application name
        image: Container image (e.g., registry/myapp:v1.0)
        port: Container port (default: 8080)
        replicas: Number of replicas (default: 1)
        namespace: Namespace (default: default)
        host: Ingress hostname (e.g., myapp.example.com)
        env_vars: Environment variables as JSON (e.g., '{"KEY": "value"}')
        enable_ingress: Create Ingress (default: True)
        auto_sync_argocd: Enable ArgoCD auto-sync (default: True)
    """
    try:
        import yaml as yaml_lib

        repo_path = "/app/projects/cluster-infrastructure"
        app_path = f"applications/{app_name}"
        results = []

        # Ensure repo exists
        if not os.path.exists(repo_path):
            return "❌ cluster-infrastructure repository not found at /app/projects/cluster-infrastructure."

        # 1. Create Deployment
        env_list = []
        if env_vars:
            env_dict = json.loads(env_vars)
            env_list = [{"name": k, "value": str(v)} for k, v in env_dict.items()]

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": app_name, "namespace": namespace, "labels": {"app": app_name}},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": app_name}},
                "template": {
                    "metadata": {"labels": {"app": app_name}},
                    "spec": {
                        "containers": [{
                            "name": app_name,
                            "image": image,
                            "ports": [{"containerPort": port, "name": "http"}],
                            "env": env_list
                        }]
                    }
                }
            }
        }

        # 2. Create Service
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": app_name, "namespace": namespace, "labels": {"app": app_name}},
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": app_name},
                "ports": [{"port": 80, "targetPort": port, "name": "http"}]
            }
        }

        # 3. Create Ingress (if enabled)
        ingress = None
        if enable_ingress and host:
            ingress = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "Ingress",
                "metadata": {
                    "name": f"{app_name}-ingress",
                    "namespace": namespace,
                    "labels": {"app": app_name},
                    "annotations": {"cert-manager.io/cluster-issuer": "letsencrypt-prod"}
                },
                "spec": {
                    "ingressClassName": "nginx",
                    "tls": [{"hosts": [host], "secretName": f"{app_name}-tls"}],
                    "rules": [{
                        "host": host,
                        "http": {
                            "paths": [{
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {"service": {"name": app_name, "port": {"number": 80}}}
                            }]
                        }
                    }]
                }
            }

        # Save YAMLs
        os.makedirs(os.path.join(repo_path, app_path), exist_ok=True)

        with open(os.path.join(repo_path, app_path, "deployment.yaml"), "w") as f:
            f.write(yaml_lib.dump(deployment, default_flow_style=False, sort_keys=False))
        results.append("✅ deployment.yaml")

        with open(os.path.join(repo_path, app_path, "service.yaml"), "w") as f:
            f.write(yaml_lib.dump(service, default_flow_style=False, sort_keys=False))
        results.append("✅ service.yaml")

        if ingress:
            with open(os.path.join(repo_path, app_path, "ingress.yaml"), "w") as f:
                f.write(yaml_lib.dump(ingress, default_flow_style=False, sort_keys=False))
            results.append("✅ ingress.yaml")

        # 4. Create ArgoCD Application
        argocd_app = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {
                "name": app_name,
                "namespace": "argocd",
                "finalizers": ["resources-finalizer.argocd.argoproj.io"]
            },
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": "https://gitea0213.kro.kr/bluemayne/cluster-infrastructure.git",
                    "targetRevision": "HEAD",
                    "path": app_path
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace
                },
                "syncPolicy": {
                    "automated": {"prune": True, "selfHeal": True} if auto_sync_argocd else None,
                    "syncOptions": ["CreateNamespace=true"]
                }
            }
        }

        argocd_path = f"argocd-applications/{app_name}.yaml"
        os.makedirs(os.path.join(repo_path, "argocd-applications"), exist_ok=True)
        with open(os.path.join(repo_path, argocd_path), "w") as f:
            f.write(yaml_lib.dump(argocd_app, default_flow_style=False, sort_keys=False))
        results.append("✅ ArgoCD Application")

        # 5. Git add, commit, push
        subprocess.run(["git", "-C", repo_path, "add", app_path, argocd_path], check=True, timeout=10)

        commit_msg = f"Deploy {app_name} to {namespace}\n\nImage: {image}\nReplicas: {replicas}"
        if host:
            commit_msg += f"\nIngress: {host}"

        subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", commit_msg],
            check=True, timeout=10
        )
        results.append("✅ Git commit")

        # Get remote URL and check if token is available
        token = os.getenv("GITEA_TOKEN", "")
        if token:
            # Set remote URL with token
            remote_url = subprocess.run(
                ["git", "-C", repo_path, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()

            if "gitea0213.kro.kr" in remote_url and token not in remote_url:
                auth_url = remote_url.replace("https://", f"https://{token}@")
                subprocess.run(["git", "-C", repo_path, "remote", "set-url", "origin", auth_url], timeout=5)

        push_result = subprocess.run(
            ["git", "-C", repo_path, "push", "origin", "HEAD"],
            capture_output=True, text=True, timeout=30
        )

        if push_result.returncode == 0:
            results.append("✅ Git push")
        else:
            results.append(f"⚠️ Git push failed: {push_result.stderr}")

        # 6. Show summary
        summary = f"""
🚀 **Application Deployed: {app_name}**

📦 **Created Files:**
{chr(10).join('  ' + r for r in results)}

📂 **Location:** `{app_path}/`

🔗 **ArgoCD:** Application `{app_name}` created in ArgoCD
   - Auto-sync: {'✅ Enabled' if auto_sync_argocd else '❌ Disabled'}
   - Namespace: `{namespace}`

🌐 **Access:** {f'https://{host}' if host else 'Service only (no Ingress)'}

⏱️ **Next Steps:**
1. ArgoCD will detect the new application automatically
2. Deployment will start in ~30 seconds
3. Check status: `kubectl get pods -n {namespace}`
"""

        return summary

    except subprocess.CalledProcessError as e:
        return f"❌ Git command failed: {e.stderr if hasattr(e, 'stderr') else str(e)}"
    except Exception as e:
        return f"❌ Deployment failed: {str(e)}"


@tool
def git_show_file_changes(repo_name: str = "cluster-infrastructure") -> str:
    """
    Show Git file changes (diff) for UI display.
    Args:
        repo_name: Repository name (default: cluster-infrastructure)
    """
    try:
        repo_path = f"/app/repos/{repo_name}"
        if not os.path.exists(repo_path):
            return f"❌ Repository not found: {repo_path}"

        # Get git status
        status_result = subprocess.run(
            ["git", "-C", repo_path, "status", "--short"],
            capture_output=True, text=True, timeout=5
        )

        # Get git diff
        diff_result = subprocess.run(
            ["git", "-C", repo_path, "diff"],
            capture_output=True, text=True, timeout=5
        )

        # Get list of untracked files with their content
        untracked_files = []
        for line in status_result.stdout.split("\n"):
            if line.startswith("??"):
                file_path = line[3:].strip()
                full_path = os.path.join(repo_path, file_path)
                if os.path.isfile(full_path):
                    with open(full_path, "r") as f:
                        content = f.read()
                    untracked_files.append({
                        "path": file_path,
                        "content": content
                    })

        output = "📝 **Git Changes**\n\n"
        output += f"**Status:**\n```\n{status_result.stdout}\n```\n\n"

        if diff_result.stdout:
            output += f"**Modified Files (Diff):**\n```diff\n{diff_result.stdout}\n```\n\n"

        if untracked_files:
            output += "**New Files:**\n\n"
            for file_info in untracked_files:
                output += f"📄 **{file_info['path']}**\n```yaml\n{file_info['content']}\n```\n\n"

        return output
    except Exception as e:
        return f"❌ Error showing changes: {str(e)}"


# MCP Tools Collection
# Read-only tools (available to ALL agents including Groq)
# ===== Universal Tools (Bash-centric, Claude Code style) =====
# All agents get the same 3 tools. Behavior is controlled by prompts, not tool restrictions.

universal_tools = [
    bash_command,  # Execute any bash command (kubectl, git, npm, python, etc.)
    read_file,     # Read files (convenience wrapper for 'cat')
    write_file,    # Write files (convenience wrapper for 'echo >')
]

# Legacy: For backward compatibility with existing specialized tools
# (These are still available but not recommended - use bash_command instead)
legacy_tools = [
    # File System
    fs_read_file,
    fs_list_directory,
    git_read_file,
    # Git
    git_list_repos,
    git_recent_commits,
    git_show_file_changes,
    git_create_file,
    git_push,
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
    # Prometheus
    prometheus_query,
    prometheus_node_metrics,
    # Docker
    docker_list_images,
    # YAML
    yaml_create_deployment,
    yaml_create_service,
    yaml_create_ingress,
    yaml_create_argocd_application,
    yaml_deploy_application,
    yaml_apply_to_cluster,
]

# For agents that might still need legacy tools during transition
all_tools = universal_tools + legacy_tools


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
                tool_func = next(t for t in all_tools if t.name == tool_name)
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
                tool_func = next(t for t in all_tools if t.name == tool_name)
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
                tool_func = next(t for t in all_tools if t.name == tool_name)
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
                tool_func = next(t for t in all_tools if t.name == tool_name)
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

