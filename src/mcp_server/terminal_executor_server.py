import json
import os
import subprocess
from typing import Optional, Tuple

from mcp.server.fastmcp import FastMCP

DEFAULT_COMMAND_TIMEOUT = 30

mcp = FastMCP("terminal_executor")


def _execute_local_command_sync(
    command: str, timeout: Optional[int] = None
) -> Tuple[Optional[str], Optional[str], int]:
    """
    로컬 시스템에서 터미널 명령어를 동기적으로 실행하고 결과를 반환합니다.
    FastMCP 도구 함수 내에서 직접 호출하기 위해 동기 함수로 만듭니다.
    """
    effective_timeout = timeout if timeout > 0 else DEFAULT_COMMAND_TIMEOUT
    print(f"\n[로컬 명령어 실행 시도]: {command} (타임아웃: {effective_timeout}초)")

    forbidden_keywords = [
        "sudo",
        "rm -rf /",
        "mkfs",
        ":(){:|:&};:",
        "mv /",
    ]

    first_word = command.strip().split(" ")[0]
    if first_word in forbidden_keywords or any(
        keyword in command for keyword in forbidden_keywords[1:]
    ):
        print(f"[보안 경고]: 위험 가능성이 있는 명령어 패턴 감지: {command}")
        return (
            None,
            f"보안 오류: 위험 가능성이 있는 명령어 '{command}'는 실행할 수 없습니다.",
            -2,
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=effective_timeout,
            cwd=os.getcwd(),
        )
        print("--- 실행 결과 ---")
        if result.stdout:
            print("[STDOUT]:")
            print(result.stdout)
        if result.stderr:
            print("[STDERR]:")
            print(result.stderr)
        print(f"[Return Code]: {result.returncode}")
        print("-----------------")
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        error_msg = f"TimeoutExpired: 명령어 실행 시간이 초과되었습니다 ({effective_timeout}초)."
        print(f"[오류]: {error_msg}")
        return None, error_msg, -1
    except Exception as e:
        error_msg = f"Exception: 명령어 실행 중 예외 발생: {e}"
        print(f"[오류]: {error_msg}")
        return None, error_msg, -1


@mcp.tool()
def execute_terminal_command(
    command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT
) -> str:
    """
    주어진 터미널 명령어를 로컬 시스템에서 실행합니다.
    보안 위험이 있을 수 있으니 주의해서 사용하세요.
    실행 결과(stdout, stderr, return code)를 JSON 문자열로 반환합니다.

    Args:
        command: 실행할 터미널 명령어 문자열.
        timeout: 명령어 실행 타임아웃 (초). 지정하지 않으면 기본값 30초가 사용됩니다.
    """
    stdout, stderr, returncode = _execute_local_command_sync(command, timeout)

    result_data = {"stdout": stdout, "stderr": stderr, "return_code": returncode}
    return json.dumps(result_data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("Terminal Executor MCP Server (FastMCP) 시작 중...")
    mcp.run(transport="stdio")
