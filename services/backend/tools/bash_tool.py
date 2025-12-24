"""
Bash 명령어 실행 도구
"""
import subprocess
from langchain_core.tools import tool
from typing import Optional


@tool
def execute_bash(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """
    Execute a bash command and return the output.

    Args:
        command: Bash command to execute
        timeout: Command timeout in seconds (default: 30)
        cwd: Working directory (default: None)

    Returns:
        Command output or error message

    Examples:
        - execute_bash("kubectl get pods -n mas")
        - execute_bash("git log -5 --oneline", cwd="/app/repos/cluster-infrastructure")
        - execute_bash("psql -U bluemayne -d postgres -c 'SELECT * FROM users LIMIT 10'")
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
def execute_ssh(command: str, host: str = "ubuntu@172.17.0.1", timeout: int = 30, use_sudo: bool = False) -> str:
    """
    Execute command on oracle-master host via SSH.

    USE THIS for accessing the host system:
    - kubectl commands (Kubernetes cluster management)
    - Accessing /home/ubuntu/Projects/ (Git repositories)
    - PostgreSQL queries (via psql)
    - Git operations on host repositories
    - File system operations on host

    Args:
        command: Command to run on the host server
        host: SSH host (default: ubuntu@172.17.0.1)
        timeout: Command timeout in seconds (default: 30)
        use_sudo: Whether to prepend 'sudo' to the command (default: False)

    Returns:
        Command output or error message

    Examples:
        - execute_ssh("kubectl get pods -n mas", use_sudo=True)
        - execute_ssh("ls -la /home/ubuntu/Projects")
        - execute_ssh("cat /home/ubuntu/Projects/mas/README.md")
        - execute_ssh("cd /home/ubuntu/Projects/mas && git log -5 --oneline")
        - execute_ssh("psql -U bluemayne -h postgresql-primary.postgresql.svc.cluster.local -d postgres -c 'SELECT version()'")
    """
    try:
        # Escape quotes in command for SSH
        escaped_command = command.replace('"', '\\"')

        # Add sudo if requested
        if use_sudo:
            escaped_command = f"sudo {escaped_command}"

        # Build SSH command
        ssh_command = f'ssh -o StrictHostKeyChecking=no {host} "{escaped_command}"'

        result = subprocess.run(
            ssh_command,
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
            return f"❌ SSH command failed (exit code {result.returncode}):\n{output}"

        return f"✅ SSH command executed successfully:\n{output}"

    except subprocess.TimeoutExpired:
        return f"❌ SSH command timed out after {timeout} seconds"
    except Exception as e:
        return f"❌ Error executing SSH command: {str(e)}"


# Export both tools
bash_tools = [execute_bash, execute_ssh]
