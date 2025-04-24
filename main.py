import os
import sys
import google.generativeai as genai
import json
import asyncio
import traceback

from dotenv import load_dotenv
from client import MultiMCPClient

try:
    from stt_service import STTService
except ImportError:
    sys.exit(1)
except RuntimeError as e:
    print(f"STT 서비스 초기화 실패: {e}")
    sys.exit(1)


load_dotenv()

try:
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key or google_api_key == "YOUR_API_KEY_HERE":
        raise ValueError(
            "환경 변수 'GOOGLE_API_KEY'가 설정되지 않았거나 유효하지 않습니다. .env 파일을 확인하세요."
        )
    genai.configure(api_key=google_api_key)

    model_name = os.getenv("MODEL_NAME")
    if not model_name:
        print(
            "경고: 환경 변수 'MODEL_NAME'이 설정되지 않았습니다. 기본값 'gemini-1.5-flash-latest'를 사용합니다."
        )
        model_name = "gemini-1.5-flash-latest"

    safety_settings_str = os.getenv("SAFETY_SETTINGS")
    safety_settings = None
    if safety_settings_str:
        try:
            safety_settings_list_of_dicts = json.loads(safety_settings_str)
            if not isinstance(safety_settings_list_of_dicts, list):
                raise ValueError(
                    "SAFETY_SETTINGS 형식이 잘못되었습니다. JSON 리스트 형식이어야 합니다."
                )
            safety_settings = safety_settings_list_of_dicts
        except json.JSONDecodeError:
            raise ValueError(
                "환경 변수 'SAFETY_SETTINGS'를 JSON으로 파싱할 수 없습니다. 형식을 확인하세요."
            )
        except Exception as e:
            raise ValueError(f"SAFETY_SETTINGS 처리 중 오류: {e}")
    else:
        print(
            "경고: 환경 변수 'SAFETY_SETTINGS'가 설정되지 않았습니다. 기본적인 안전 설정을 사용합니다."
        )
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
        ]

    generation_config_str = os.getenv("GENERATION_CONFIG")
    generation_config = None
    if generation_config_str:
        try:
            generation_config_dict = json.loads(generation_config_str)
            if not isinstance(generation_config_dict, dict):
                raise ValueError(
                    "GENERATION_CONFIG 형식이 잘못되었습니다. JSON 객체 형식이어야 합니다."
                )
            generation_config = generation_config_dict
        except json.JSONDecodeError:
            raise ValueError(
                "환경 변수 'GENERATION_CONFIG'를 JSON으로 파싱할 수 없습니다."
            )
        except Exception as e:
            raise ValueError(f"GENERATION_CONFIG 처리 중 오류: {e}")

    mcp_config_path = "mcp_config.json"
    if not os.path.exists(mcp_config_path):
        raise FileNotFoundError(
            f"MCP 설정 파일 '{mcp_config_path}'을 찾을 수 없습니다."
        )
    with open(mcp_config_path, "r") as f:
        mcp_config = json.load(f)
        mcp_servers = mcp_config.get("mcpServers")
        if not mcp_servers or not isinstance(mcp_servers, dict):
            raise ValueError(
                f"'{mcp_config_path}' 파일에 'mcpServers' 객체가 없거나 형식이 잘못되었습니다."
            )

    whisper_model_name = os.getenv("WHISPER_MODEL", "base")
    if whisper_model_name == "base":
        print(
            "경고: 환경 변수 'WHISPER_MODEL'이 설정되지 않았습니다. 기본값 'base' 모델을 사용합니다."
        )
    else:
        print(
            f"환경 변수 'WHISPER_MODEL'에서 '{whisper_model_name}' 모델을 사용합니다."
        )

    whisper_device_pref = os.getenv("WHISPER_DEVICE", "auto").lower()
    if whisper_device_pref not in ["auto", "cpu", "mps"]:
        print(
            f"경고: WHISPER_DEVICE 환경 변수 값 '{whisper_device_pref}'이(가) 유효하지 않습니다. 'auto' 설정을 사용합니다."
        )
        whisper_device_pref = "auto"
    else:
        print(f"환경 변수 'WHISPER_DEVICE' 설정: '{whisper_device_pref}'")


except (ValueError, FileNotFoundError) as e:
    print(f"오류: 설정 로드 실패 - {e}")
    sys.exit(1)
except Exception as e:
    print(f"설정 중 예기치 않은 오류 발생: {e}")
    traceback.print_exc()
    sys.exit(1)


SYSTEM_PROMPT = """
You are a highly capable AI assistant integrated with tools via the Model Context Protocol (MCP). Your primary function is to understand the user's request and **execute the appropriate MCP tool** to fulfill it. You MUST use the available tools whenever possible and relevant. Do NOT provide conversational answers if a tool can perform the requested action.

Available Tools:
You have access to tools provided by connected MCP servers. You MUST analyze the user's request and determine if any available tool can fulfill it. If a suitable tool exists, you MUST call that tool's function with the correct arguments.

**Critical Instructions:**
1.  **Analyze and Execute:** Carefully analyze the user's request. If the request involves actions like file operations (reading, writing, listing), running terminal commands, searching, or other tasks matching an available tool's description, you **MUST** call the corresponding tool function.
2.  **Prioritize Tool Use:** Do not answer requests directly if a tool can perform the task. For example, if the user asks to "list files", call the `list_directory` tool instead of saying "I can list files for you". If the user asks to "run finder", call the `execute_terminal_command` tool with the appropriate command string.
3.  **Terminal Commands:** For requests that require executing a terminal command (like opening applications, running scripts, managing processes), you **MUST** use the `execute_terminal_command` tool. Provide the exact command string needed for the `command` argument.
4.  **Argument Accuracy:** When calling a tool, ensure all required arguments are provided correctly based on the tool's schema.
5.  **Clarification:** If the request is ambiguous or lacks necessary information to use a tool (e.g., missing file path), ask the user for clarification. Do not attempt to guess or use a tool with incomplete information.
6.  **Safety First:** Never use tools in a way that could harm the user's system or data. If a request seems unsafe or beyond the tools' capabilities, explain why you cannot fulfill it.
7.  **Response Language:** Respond in Korean. Tool function calls themselves use standard naming conventions.

Your goal is to act as an efficient agent, leveraging the provided tools to accomplish tasks, not just to chat. Process the user's request and determine the necessary tool call.
"""


async def main():
    """
    메인 비동기 애플리케이션 로직
    """
    print("\n로컬 AI 에이전트 (MCP 클라이언트 + Whisper STT 연동)")

    mcp_client = None
    stt_service = None

    try:
        stt_service = STTService(
            model_name=whisper_model_name,
            device_preference=whisper_device_pref,
        )

        mcp_client = MultiMCPClient(
            model_name=model_name,
            safety_settings=safety_settings,
            generation_config=generation_config,
            system_instruction=SYSTEM_PROMPT,
        )

        print("\nMCP 서버 연결 시도 중...")
        await mcp_client.connect_all_servers(mcp_servers)

        if not mcp_client.sessions:
            print("경고: 연결된 MCP 서버가 없습니다. 도구 사용이 제한됩니다.")
        else:
            tool_names = [t.name for t in mcp_client.all_mcp_tools]
            print(f"\n사용 가능한 MCP 도구 ({len(tool_names)}개): {tool_names}")

        print("\n(종료하려면 'exit' 또는 Ctrl+C 입력)")

        while True:
            user_input = ""
            try:
                choice = await asyncio.to_thread(
                    input,
                    "\n요청사항을 입력하거나, 's'를 눌러 음성 입력을 시작하세요: ",
                )
                choice = choice.strip().lower()

                if choice == "exit":
                    print("앱을 종료합니다.")
                    break
                elif choice == "s":
                    audio_data = await asyncio.to_thread(stt_service.record_audio)
                    if audio_data is not None:
                        user_input = await asyncio.to_thread(
                            stt_service.transcribe_audio, audio_data
                        )
                        print(f"\n음성 인식 결과: {user_input}")
                    else:
                        print("오디오 녹음에 실패했거나 데이터가 없습니다.")
                        continue
                elif choice:
                    user_input = choice
                else:
                    continue

                if not user_input:
                    print("입력된 내용이 없습니다.")
                    continue

                print("\nAI에게 처리 요청 중...")
                ai_response = await mcp_client.process_query(user_input)

                print("\n--- AI 응답 ---")
                print(ai_response)
                print("---------------")

            except EOFError:
                print("\n입력 스트림이 닫혔습니다. 앱을 종료합니다.")
                if stt_service:
                    stt_service.stop_recording()
                break
            except KeyboardInterrupt:
                print("\nCtrl+C 입력 감지. 앱을 종료합니다.")
                if stt_service:
                    stt_service.stop_recording()
                break
            except Exception as e:
                print(f"\n루프 중 예상치 못한 오류 발생: {e}")
                traceback.print_exc()
                if stt_service:
                    stt_service.stop_recording()

    except RuntimeError as e:
        print(f"애플리케이션 초기화 오류: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"\n애플리케이션 시작 중 심각한 오류 발생: {e}")
        traceback.print_exc()
    finally:
        print("\n애플리케이션 종료 처리 중...")
        if stt_service:
            stt_service.stop_recording()
        if mcp_client:
            await mcp_client.cleanup()
        print("애플리케이션 종료 완료.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램 강제 종료 확인.")
    except Exception as e:
        print(f"\n최상위 레벨 오류 발생: {e}")
        traceback.print_exc()
