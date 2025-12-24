"""
Bash 명령어 실행 도구
"""
import subprocess
from langchain_core.tools import tool
from typing import Optional


@tool
def execute_bash(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """
    Execute a bash command in the container.

    Args:
        command: Bash command to execute
        timeout: Command timeout in seconds (default: 30)
        cwd: Working directory (default: None)

    Returns:
        Command output or error message

    Examples:
        - execute_bash("ls -la /app")
        - execute_bash("python --version")
        - execute_bash("curl -s http://prometheus:9090/api/v1/query?query=up")
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]:\n{result.stderr}"

        if result.returncode != 0:
            return f"❌ Command failed (exit code {result.returncode}):\n{output}"

        return f"✅ Command executed successfully:\n{output}"

    except subprocess.TimeoutExpired:
        return f"❌ Command timed out after {timeout} seconds"
    except Exception as e:
        return f"❌ Error executing command: {str(e)}"


@tool
def execute_host(command: str, timeout: int = 30, use_sudo: bool = False) -> str:
    """
    Execute command on the HOST system using nsenter (NO SSH needed!).

    USE THIS for accessing the host system:
    - kubectl commands (Kubernetes cluster management)
    - Accessing /home/ubuntu/Projects/ (Git repositories)
    - PostgreSQL queries (via psql)
    - Git operations on host repositories
    - File system operations on host
    - ALL host system operations

    This works by entering the host's namespaces directly from the container.
    Much faster than SSH and no authentication needed!

    Args:
        command: Command to run on the host system
        timeout: Command timeout in seconds (default: 30)
        use_sudo: Whether to prepend 'sudo' to the command (default: False)

    Returns:
        Command output or error message

    Examples:
        - execute_host("kubectl get pods -n mas", use_sudo=True)
        - execute_host("ls -la /home/ubuntu/Projects")
        - execute_host("cat /home/ubuntu/Projects/mas/README.md")
        - execute_host("cd /home/ubuntu/Projects/mas && git log -5 --oneline")
        - execute_host("psql -U bluemayne -h postgresql-primary.postgresql.svc.cluster.local -d postgres -c 'SELECT version()'")
    """
    try:
        # Use nsenter to enter host namespaces
        # -t 1: target PID 1 (init process on host)
        # -m: mount namespace
        # -u: UTS namespace (hostname)
        # -n: network namespace
        # -i: IPC namespace
        # Run as ubuntu user to avoid git "dubious ownership" errors
        # Use 'su - ubuntu -c' for user commands, 'sudo' for privileged commands
        if use_sudo:
            # For sudo commands, run directly with sudo
            nsenter_command = f"nsenter -t 1 -m -u -n -i -- sh -c {subprocess.list2cmdline([f'sudo {command}'])}"
        else:
            # For regular commands, run as ubuntu user
            nsenter_command = f"nsenter -t 1 -m -u -n -i -- su - ubuntu -c {subprocess.list2cmdline([command])}"

        result = subprocess.run(
            nsenter_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]:\n{result.stderr}"

        if result.returncode != 0:
            return f"❌ Host command failed (exit code {result.returncode}):\n{output}"

        return f"✅ Host command executed successfully:\n{output}"

    except subprocess.TimeoutExpired:
        return f"❌ Host command timed out after {timeout} seconds"
    except Exception as e:
        return f"❌ Error executing host command: {str(e)}"


# Export both tools
bash_tools = [execute_bash, execute_host]
