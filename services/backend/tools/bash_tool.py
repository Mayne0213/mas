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


# Export the tool
bash_tools = [execute_bash]
