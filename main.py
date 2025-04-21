import os
import requests # requests는 pyproject.toml에 추가했으므로 사용 가능
import subprocess
import google.generativeai as genai
# config 모듈 import
import config # 설정 파일 import

# Google AI 설정 (config.py 에서 로드)
try:
    # API 키 존재 및 기본값 여부 확인
    if not hasattr(config, 'GOOGLE_API_KEY') or not config.GOOGLE_API_KEY or config.GOOGLE_API_KEY == "YOUR_API_KEY_HERE":
        print("오류: config.py 파일에 GOOGLE_API_KEY가 설정되지 않았거나 유효하지 않습니다.")
        print("config.py 파일을 열어 API 키를 올바르게 입력해주세요.")
        exit(1)
    genai.configure(api_key=config.GOOGLE_API_KEY)
except AttributeError:
    print("오류: config.py 파일에서 GOOGLE_API_KEY 변수를 찾을 수 없습니다.")
    exit(1)
except Exception as e:
    print(f"Google AI 설정 중 오류 발생: {e}")
    exit(1)

# 사용할 모델 설정 (config.py 에서 로드)
try:
    # 모델 이름과 안전 설정 존재 여부 확인
    if not hasattr(config, 'MODEL_NAME') or not hasattr(config, 'SAFETY_SETTINGS'):
         raise AttributeError("config.py에 MODEL_NAME 또는 SAFETY_SETTINGS가 정의되지 않았습니다.")
    model = genai.GenerativeModel(config.MODEL_NAME, safety_settings=config.SAFETY_SETTINGS)
except AttributeError as e:
     print(f"오류: {e}")
     exit(1)
except Exception as e:
    print(f"AI 모델 로드 중 오류 발생: {e}")
    exit(1)


# 시스템 프롬프트 (AI에게 역할과 제약 조건 부여)
# 이전 버전과 동일하게 유지 (내용 생략 - 실제 코드에는 포함됨)
SYSTEM_PROMPT = """
You are an AI agent designed to assist the user by performing tasks on their computer. You achieve this by interpreting the user's natural language requests and generating a single, appropriate terminal command that the user's local application will then execute on your behalf. You use the terminal as a tool to access and manipulate computer resources (files, folders, processes, etc.). Your primary operating environment is macOS.

**Your Goal:**
Understand the user's intent and generate the single best terminal command to fulfill that intent in a safe manner.

**Absolute Safety Directives (Non-negotiable):**
1.  **PRIORITY 1: SAFETY.** NEVER generate commands that could harm the user's system, compromise data, or violate privacy.
2.  **FORBIDDEN ACTIONS:** You are strictly prohibited from generating commands that:
    * Modify or delete system files or directories (e.g., anything under `/`, `/etc`, `/usr`, `/System` - listing these is generally acceptable, but modification/deletion is not).
    * Modify network configurations.
    * Modify user accounts or permissions.
    * Attempt to gain elevated privileges (e.g., commands involving `sudo` or `pkexec`).
    * Perform recursive destructive operations without very specific, limited, and pre-defined targets (e.g., be extremely cautious with `rm -rf`).
    * Download and execute arbitrary external files.
3.  You are an agent suggesting actions via commands; the user's application will validate and confirm execution. Do not attempt to simulate execution or describe results you haven't confirmed via a real terminal output (which you cannot directly access).

**Interpreting User Requests (as an Agent):**
- Analyze the user's request to understand the underlying task or goal (e.g., "find a file", "organize downloads", "get system info").
- Determine if this task can be accomplished safely and effectively with a *single* terminal command on macOS.

**Output Format (Strict Requirements for App Processing):**
Your response MUST be formatted using one of the following structures ONLY:

1.  **Task Action Proposed (Command Generated):**
    If you successfully determine a safe and appropriate single command to perform the user's requested task, output:
    ```
    <CMD>
    [Generated Terminal Command String]
    </CMD>
    <CMD_EXPLANATION>
    [사용자의 요청을 처리하기 위해 이 명령어를 선택한 이유와 이 명령어가 수행할 작업을 한국어로 설명합니다.]
    </CMD_EXPLANATION>
    ```
    * `[Generated Terminal Command String]`: The exact, executable command for macOS (e.g., `ls -l`, `cd Documents`, `mkdir new_folder`). Do NOT include conversational text or markdown formatting outside the `<CMD>` tags for the command itself. The command string must be parsable by the application.
    * `[사용자의 요청을 처리하기 위해...]`: A clear, concise explanation in Korean of *what the command does* and *why you chose it* based on the user's request. This helps the user understand and confirm.

2.  **Clarification Needed (Cannot Proceed):**
    If the user's request is unclear, ambiguous, or requires more information for you to determine a specific action or command, output:
    ```
    <CLARIFICATION>
    [에이전트로서 작업을 수행하기 위해 어떤 정보가 더 필요한지 사용자에게 구체적이고 친절하게 한국어로 질문합니다. 예: "어떤 파일에 대해 작업할까요?", "이 작업을 수행할 폴더는 어디인가요?"]
    </CLARIFICATION>
    ```
    * `[에이전트로서 작업을 수행하기 위해...]`: A specific question or statement requesting necessary information in Korean.

3.  **Task Cannot Be Fulfilled (Error / Unsafe / Beyond Capability):**
    If the user's request is impossible, beyond your current capability as an agent using single terminal commands, requires multiple complex steps, or violates the absolute safety directives, output:
    ```
    <ERROR>
    [요청을 에이전트로서 처리할 수 없는 이유를 한국어로 명확하고 안전하게 설명합니다. 보안 정책 위반인 경우 그 점을 명시하세요. 예: "죄송합니다. 해당 작업은 보안상 위험하여 수행할 수 없습니다.", "이 작업은 여러 단계를 거쳐야 하거나 제가 단일 명령어로 수행할 수 있는 범위를 넘어섭니다.", "요청 내용을 이해했지만, 현재 기능으로는 수행하기 어렵습니다."]
    </ERROR>
    ```
    * `[요청을 에이전트로서 처리할 수 없는 이유를...]`: A clear explanation in Korean of *why* the task cannot be done by the agent via a single command, mentioning safety or capability limits if applicable.

**General Agent Behavior:**
- Be task-oriented. Focus on understanding the user's goal.
- Prioritize safety above all else. When in doubt, output `<ERROR>`.
- Generate only one command per request if a command is possible.
- All explanatory text, questions, and error messages must be in Korean. The command string itself must be the standard terminal syntax.
- Do not include any conversational filler before or after the defined tags.

**Now, process the user's request provided in the next input.**
"""

def get_ai_command(user_prompt):
    """
    사용자 프롬프트를 받아 AI 모델에게 적절한 터미널 명령어를 생성하도록 요청합니다.
    """
    try:
        # 시스템 프롬프트와 사용자 프롬프트를 결합하여 전달
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser Request: {user_prompt}"
        response = model.generate_content(full_prompt)

        # 응답 텍스트 추출 및 후처리 (앞뒤 공백 제거)
        ai_response_text = response.text.strip()
        return ai_response_text

    except Exception as e:
        print(f"AI 명령어 생성 중 오류 발생: {e}")
        # 오류 발생 시 <ERROR> 태그를 포함한 메시지 반환
        return f"<ERROR>\nAI 모델 호출 중 오류가 발생했습니다: {e}\n</ERROR>"


def execute_command(command):
    """
    주어진 터미널 명령어를 실행하고 결과를 반환합니다.
    보안상 위험할 수 있으므로 주의해서 사용해야 합니다.
    """
    print(f"\n[명령어 실행 시도]: {command}")
    command_timeout = 30 # 기본 타임아웃 값
    try:
        # config 파일에서 타임아웃 값 읽기 시도
        if hasattr(config, 'COMMAND_TIMEOUT') and isinstance(config.COMMAND_TIMEOUT, (int, float)) and config.COMMAND_TIMEOUT > 0:
            command_timeout = config.COMMAND_TIMEOUT
        else:
            print("[경고]: config.py의 COMMAND_TIMEOUT이 유효하지 않거나 없습니다. 기본값 30초를 사용합니다.")

        # shell=True는 보안 위험을 증가시킬 수 있으므로 신중하게 사용
        # 여기서는 AI가 생성한 단일 명령어를 실행하기 위해 사용
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False, # check=True로 하면 오류 발생 시 예외 발생
            timeout=command_timeout # 설정된 타임아웃 사용
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
        print(f"[오류]: 명령어 실행 시간이 초과되었습니다 ({command_timeout}초).")
        return None, f"TimeoutExpired: 명령어 실행 시간이 초과되었습니다 ({command_timeout}초).", -1 # 타임아웃 시 특별한 리턴 코드
    except Exception as e:
        print(f"[오류]: 명령어 실행 중 예외 발생: {e}")
        return None, f"Exception: {e}", -1 # 일반 예외 시 특별한 리턴 코드

def parse_ai_response(ai_response):
    """
    AI 응답에서 <CMD>, <CMD_EXPLANATION>, <CLARIFICATION>, <ERROR> 태그를 파싱합니다.
    """
    command = None
    explanation = None
    clarification = None
    error = None

    # 태그 파싱 로직 (이전 버전과 동일)
    if "<CMD>" in ai_response and "</CMD>" in ai_response:
        start_cmd = ai_response.find("<CMD>") + len("<CMD>")
        end_cmd = ai_response.find("</CMD>")
        command = ai_response[start_cmd:end_cmd].strip()

        if "<CMD_EXPLANATION>" in ai_response and "</CMD_EXPLANATION>" in ai_response:
            start_exp = ai_response.find("<CMD_EXPLANATION>") + len("<CMD_EXPLANATION>")
            end_exp = ai_response.find("</CMD_EXPLANATION>")
            explanation = ai_response[start_exp:end_exp].strip()
        else:
            explanation = "(설명 없음)" # 설명 태그가 없는 경우

    elif "<CLARIFICATION>" in ai_response and "</CLARIFICATION>" in ai_response:
        start_clar = ai_response.find("<CLARIFICATION>") + len("<CLARIFICATION>")
        end_clar = ai_response.find("</CLARIFICATION>")
        clarification = ai_response[start_clar:end_clar].strip()

    elif "<ERROR>" in ai_response and "</ERROR>" in ai_response:
        start_err = ai_response.find("<ERROR>") + len("<ERROR>")
        end_err = ai_response.find("</ERROR>")
        error = ai_response[start_err:end_err].strip()
    else:
        # 예상치 못한 형식의 응답 처리
        error = f"AI 응답 형식이 올바르지 않습니다:\n{ai_response}"


    return command, explanation, clarification, error


def main():
    """
    메인 애플리케이션 로직
    """
    print("로컬 에이전트 앱 (종료하려면 'exit' 입력)")

    while True:
        try:
            user_input = input("\n요청사항을 입력하세요: ")
            if user_input.lower() == 'exit':
                print("앱을 종료합니다.")
                break
            if not user_input:
                continue

            print("\nAI에게 명령어 생성을 요청합니다...")
            ai_response = get_ai_command(user_input)

            print("\n--- AI 응답 ---")
            print(ai_response)
            print("---------------")

            command, explanation, clarification, error = parse_ai_response(ai_response)

            if command:
                print(f"\n[AI 제안 명령어]: {command}")
                print(f"[설명]: {explanation}")
                # 사용자 확인 절차 (보안 강화)
                confirm = input("이 명령어를 실행하시겠습니까? (y/n): ").lower()
                if confirm == 'y':
                    execute_command(command)
                else:
                    print("명령어 실행이 취소되었습니다.")
            elif clarification:
                print(f"\n[AI 요청]: {clarification}")
                # 사용자가 다음 입력에서 추가 정보 제공
            elif error:
                print(f"\n[AI 오류]: {error}")
            else:
                # 파싱 실패 또는 예상치 못한 응답
                 print("\n[오류]: AI로부터 유효한 응답을 받지 못했습니다.")


        except EOFError:
            print("\n입력 스트림이 닫혔습니다. 앱을 종료합니다.")
            break
        except KeyboardInterrupt:
            print("\nCtrl+C 입력 감지. 앱을 종료합니다.")
            break
        except Exception as e:
            print(f"\n예상치 못한 오류 발생: {e}")
            # 오류 발생 시에도 계속 실행되도록 루프 유지 (선택 사항)
            # break # 또는 루프 종료


if __name__ == "__main__":
    main()
