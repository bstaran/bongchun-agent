import asyncio
import traceback
import queue
import threading
from typing import Optional, Any
import os

from .client import MultiMCPClient
from .app_config import load_config, NO_PROMPT_OPTION
from .prompt_manager import PromptManager
from .stt_service import STTService

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gui import ChatGUI


class AppController:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        config: dict,
        prompt_manager: PromptManager,
    ):
        self.gui: Optional["ChatGUI"] = None
        self.loop = loop
        self.config = config
        self.prompt_manager = prompt_manager
        self.response_queue = queue.Queue()
        self.attached_file_path: Optional[str] = None
        self.model_name = self.config.get("model_name")
        self.safety_settings = self.config.get("safety_settings")
        self.generation_config = self.config.get("generation_config")
        self.mcp_servers = self.config.get("mcp_servers")
        self.whisper_model_name = self.config.get("whisper_model_name")
        self.whisper_device_pref = self.config.get("whisper_device_pref")
        self.stt_provider = self.config.get("stt_provider")

        self.mcp_client: Optional[MultiMCPClient] = None
        self.stt_service: Optional[STTService] = None

        self._initialize_services()

        if self.mcp_client:
            print("\nAppController: MCP 서버 연결 시도 중 (백그라운드)...")
            asyncio.run_coroutine_threadsafe(self._connect_mcp_servers(), self.loop)

    def set_gui(self, gui: "ChatGUI"):
        """ChatGUI 인스턴스를 설정합니다."""
        self.gui = gui
        print("AppController: GUI 참조 설정 완료.")
        if self.mcp_client and self.mcp_client.sessions:
            tool_names = [t.name for t in self.mcp_client.all_mcp_tools]
            self.response_queue.put(
                f"System: MCP 서버 연결됨. 사용 가능 도구: {len(tool_names)}개"
            )
        elif self.mcp_client and not self.mcp_client.sessions:
            self.response_queue.put(
                "System: 경고: 연결된 MCP 서버가 없습니다. 도구 사용이 제한됩니다."
            )

    def _initialize_services(self):
        """MCP 클라이언트와 STT 서비스 초기화 (self.config 사용)"""
        try:
            stt_provider = self.config.get("stt_provider")
            whisper_model = self.config.get("whisper_model_name")
            whisper_device = self.config.get("whisper_device_pref")
            try:
                print(
                    f"AppController: STT 서비스 초기화 시도 (제공자: {stt_provider})..."
                )
                self.stt_service = STTService(
                    provider=stt_provider,
                    whisper_model_name=whisper_model,
                    whisper_device_preference=whisper_device,
                )
                print(f"AppController: STT 서비스 ({stt_provider}) 초기화 완료.")
            except NameError:
                print("AppController 오류: STTService 클래스를 import할 수 없습니다.")
                self.stt_service = None
            except ImportError as ie:
                print(f"AppController 오류: STT 서비스 의존성 로드 실패 ({ie}).")
                self.stt_service = None
            except RuntimeError as e:
                print(
                    f"AppController 경고: STT 서비스 ({stt_provider}) 초기화 실패 ({e})."
                )
                self.stt_service = None

            # MCP 클라이언트 초기화
            model_name = self.config.get("model_name")
            safety_settings = self.config.get("safety_settings")
            generation_config = self.config.get("generation_config")
            system_instruction = self.prompt_manager.default_system_prompt

            self.mcp_client = MultiMCPClient(
                model_name=model_name,
                safety_settings=safety_settings,
                generation_config=generation_config,
                system_instruction=system_instruction,
            )
            if system_instruction:
                print(
                    "AppController: MCP 클라이언트 초기화 완료 (기본 시스템 프롬프트 적용됨)."
                )
            else:
                print(
                    "AppController: MCP 클라이언트 초기화 완료 (기본 시스템 프롬프트 없음)."
                )

        except Exception as e:
            print(f"AppController: 서비스 초기화 중 심각한 오류: {e}")
            traceback.print_exc()
            self.response_queue.put(f"System: 치명적 오류: 서비스 초기화 실패 - {e}")

    async def _connect_mcp_servers(self):
        """비동기 MCP 서버 연결"""
        if not self.mcp_client:
            print("AppController: MCP 클라이언트가 없어 서버에 연결할 수 없습니다.")
            return
        try:
            await self.mcp_client.connect_all_servers(self.mcp_servers)
            if not self.mcp_client.sessions:
                print("AppController 경고: 연결된 MCP 서버가 없습니다.")
                self.response_queue.put(
                    "System: 경고: 연결된 MCP 서버가 없습니다. 도구 사용이 제한됩니다."
                )
            else:
                tool_names = [t.name for t in self.mcp_client.all_mcp_tools]
                print(
                    f"AppController: 사용 가능한 MCP 도구 ({len(tool_names)}개): {tool_names}"
                )
                self.response_queue.put(
                    f"System: MCP 서버 연결됨. 사용 가능 도구: {len(tool_names)}개"
                )
        except Exception as e:
            print(f"AppController: MCP 서버 연결 오류: {e}")
            self.response_queue.put(f"System: 오류: MCP 서버 연결 실패 - {e}")
            traceback.print_exc()

    async def _process_ai_query(
        self,
        query: str,
        additional_prompt: Optional[str],
        file_path: Optional[str] = None,
    ):
        """비동기로 AI 쿼리 처리"""
        if not self.mcp_client:
            self.response_queue.put(
                "System: 오류: MCP 클라이언트가 준비되지 않았습니다."
            )
            self.response_queue.put("System: Buttons enabled")
            return

        try:
            self.response_queue.put("System: AI 처리 중...")
            ai_response = await self.mcp_client.process_query(
                query, additional_prompt=additional_prompt, file_path=file_path
            )
            self.response_queue.put(f"AI\n{ai_response}")
        except Exception as e:
            self.response_queue.put(f"System: AI 처리 중 오류 발생: {e}")
            traceback.print_exc()
        finally:
            self.attached_file_path = None
            self.response_queue.put("System: Clear attachment label")
            self.response_queue.put("System: Buttons enabled")

    def _run_stt_in_thread(self, additional_prompt: Optional[str]):
        """STT 작업을 별도 스레드에서 실행"""
        user_input = None
        try:
            if not self.stt_service:
                self.response_queue.put(
                    "System: 오류: STT 서비스가 준비되지 않았습니다."
                )
                return

            audio_data = self.stt_service.record_audio()
            if audio_data is not None and audio_data.size > 0:
                user_input = self.stt_service.transcribe_audio(audio_data)
                if user_input:
                    self.response_queue.put(f"User\n{user_input}")

                    current_file_path = self.attached_file_path
                    asyncio.run_coroutine_threadsafe(
                        self._process_ai_query(
                            user_input,
                            additional_prompt,
                            file_path=current_file_path,
                        ),
                        self.loop,
                    )
                else:
                    self.response_queue.put("System: 음성을 인식하지 못했습니다.")
            else:
                self.response_queue.put("System: 오디오 녹음 실패 또는 취소됨.")
        except Exception as e:
            self.response_queue.put(f"System: 음성 입력 중 오류: {e}")
            traceback.print_exc()
        finally:
            if not user_input:
                self.response_queue.put("System: Buttons enabled")
            self.response_queue.put("System: Hide recording status")

    def _start_new_chat(self) -> bool:
        """새로운 채팅 세션을 시작합니다."""
        if not self.mcp_client:
            print("AppController 오류: 새 채팅 시작 실패 - MCP 클라이언트 없음")
            self.response_queue.put("System: 오류: 새 채팅 시작 실패 - 클라이언트 없음")
            return False

        try:
            if hasattr(self.mcp_client, "start_new_chat"):
                self.mcp_client.start_new_chat()
                print("AppController: MCP Client chat history reset.")
            else:
                print(
                    "AppController 경고: MCP Client에 'start_new_chat' 메서드가 없습니다."
                )

            self.attached_file_path = None
            print("AppController: 새로운 채팅 세션 시작됨.")
            self.response_queue.put("System: 새 채팅 시작됨.")
            return True
        except Exception as e:
            error_msg = f"새로운 채팅 세션을 시작하는 데 실패했습니다: {e}"
            print(f"AppController 오류: {error_msg}")
            traceback.print_exc()
            self.response_queue.put(f"System: 오류: {error_msg}")
            return False

    # --- GUI 이벤트 핸들러에서 호출될 메서드들 ---

    def process_user_request(self, user_request: str, additional_prompt: Optional[str]):
        """사용자 텍스트 요청 처리"""
        if not self.mcp_client:
            self.response_queue.put(
                "System: 오류: MCP 클라이언트가 준비되지 않았습니다."
            )
            self.response_queue.put("System: Buttons enabled")
            return

        self.response_queue.put(f"User\n{user_request}")

        current_file_path = self.attached_file_path

        asyncio.run_coroutine_threadsafe(
            self._process_ai_query(
                user_request, additional_prompt, file_path=current_file_path
            ),
            self.loop,
        )

    def handle_voice_input(self):
        """음성 입력 요청 처리"""
        if not self.stt_service:
            self.response_queue.put("System: 오류: STT 서비스가 준비되지 않았습니다.")
            return

        self.response_queue.put("System: Show recording status")
        self.response_queue.put("System: Buttons disabled")

        additional_prompt = None
        if self.gui:
            selected_prompt_display = self.gui.prompt_var.get()
            additional_prompt = self.prompt_manager.load_selected_prompt(
                selected_prompt_display
            )
        else:
            print("AppController 경고: handle_voice_input 호출 시 GUI가 설정되지 않음.")
            additional_prompt = self.prompt_manager.default_system_prompt

        threading.Thread(
            target=self._run_stt_in_thread, args=(additional_prompt,), daemon=True
        ).start()

    def start_new_chat_session(self) -> bool:
        """새 채팅 세션 시작 요청 처리"""
        if self.gui:
            self.response_queue.put("System: Clear chat display")
        return self._start_new_chat()

    def attach_file(self, filepath: str):
        """파일 첨부 요청 처리"""
        self.attached_file_path = filepath
        filename = os.path.basename(filepath)
        print(f"AppController: 파일 첨부됨 - {filename}")
        self.response_queue.put(f"System: Set attachment label|{filename}")

    async def cleanup(self):
        """애플리케이션 종료 시 리소스 정리"""
        print("AppController: 정리 시작...")
        if self.mcp_client:
            print("AppController: MCP 클라이언트 정리 중...")
            await self.mcp_client.cleanup()
            print("AppController: MCP 클라이언트 정리 완료.")

        if self.stt_service:
            print("AppController: STT 서비스 정리 중...")
            if hasattr(self.stt_service, "stop_recording") and callable(
                getattr(self.stt_service, "stop_recording", None)
            ):
                try:
                    self.stt_service.stop_recording()
                except Exception as e:
                    print(f"AppController 경고: STT 서비스 정리 중 오류: {e}")
            print("AppController: STT 서비스 정리 완료.")
        print("AppController: 정리 완료.")
