import asyncio
import traceback
import queue
import threading
from typing import Optional
import os

from .client import MultiMCPClient
from .prompt_manager import PromptManager
from .stt_service import STTService
from .hotkey_manager import HotkeyManager

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
        self.attached_files: list[str] = []
        self.model_name = self.config.get("model_name")
        self.safety_settings = self.config.get("safety_settings")
        self.generation_config = self.config.get("generation_config")
        self.mcp_servers = self.config.get("mcp_servers")
        self.whisper_model_name = self.config.get("whisper_model_name")
        self.whisper_device_pref = self.config.get("whisper_device_pref")
        self.stt_provider = self.config.get("stt_provider")

        self.mcp_client: Optional[MultiMCPClient] = None
        self.stt_service: Optional[STTService] = None
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.is_first_request = True

        self._initialize_services()

        if self.mcp_client:
            print("\nAppController: MCP 서버 연결 시도 중 (백그라운드)...")
            asyncio.run_coroutine_threadsafe(self._connect_mcp_servers(), self.loop)

    def set_gui(self, gui: "ChatGUI"):
        """ChatGUI 인스턴스를 설정하고 단축키 리스너를 시작합니다."""
        self.gui = gui
        print("AppController: set_gui() 메서드 시작.")
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

        if self.hotkey_manager:
            if self.hotkey_manager.keyboard_available:
                print("AppController: 단축키 리스너 시작 시도...")
                print("AppController: hotkey_manager.start_listener() 호출 시도...")
                self.hotkey_manager.start_listener()
                print("AppController: hotkey_manager.start_listener() 호출 완료.")
                print("AppController: 단축키 리스너 시작됨.")
            else:
                print(
                    "AppController 경고: pynput 키보드 리스너를 사용할 수 없습니다. 단축키 비활성화됨."
                )
                self.response_queue.put(
                    "System: 경고: 키보드 입력 감지 불가. 단축키 비활성화됨."
                )
        print("AppController: set_gui() 메서드 종료.")

    def _initialize_services(self):
        """MCP 클라이언트, STT 서비스, HotkeyManager 초기화"""
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

            try:
                print("AppController: HotkeyManager 초기화 시도...")
                self.hotkey_manager = HotkeyManager()
                print("AppController: HotkeyManager 초기화 완료.")
                self.hotkey_manager.register_hotkeys(
                    activate=True, show_window=True, paste=False
                )
                print("AppController: 전역 단축키 (음성, 창 토글) 등록 완료.")
            except ImportError:
                print(
                    "AppController 오류: HotkeyManager 클래스를 import할 수 없습니다."
                )
                self.hotkey_manager = None
            except Exception as e:
                print(f"AppController 경고: HotkeyManager 초기화 실패 ({e}).")
                traceback.print_exc()
                self.hotkey_manager = None
                self.response_queue.put(
                    f"System: 경고: 단축키 관리자 초기화 실패 - {e}"
                )

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
        file_paths: Optional[list[str]] = None,
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

            # 1. 첫 요청인지 확인하고 default 프롬프트 추가
            system_prefix = ""
            if self.is_first_request and self.prompt_manager.default_system_prompt:
                system_prefix = (
                    f"{self.prompt_manager.default_system_prompt}\n\n---\n\n"
                )
                print("[DEBUG] Adding default system prompt for the first request.")
                self.is_first_request = False

            # 2. 선택된 *추가* 프롬프트 이름(additional_prompt)으로 실제 내용 로드
            loaded_additional_prompt_content = ""
            if additional_prompt:
                loaded_additional_prompt_content = (
                    self.prompt_manager.load_selected_prompt(additional_prompt)
                )
                if loaded_additional_prompt_content:
                    print(
                        f"[DEBUG] Loaded additional prompt content for '{additional_prompt}'"
                    )
                else:
                    print(
                        f"[DEBUG] Failed to load content for additional prompt '{additional_prompt}', using empty string."
                    )

            # 3. 시스템 프롬프트(첫 요청 시), 추가 프롬프트, 사용자 쿼리 결합
            final_query = query
            prompt_parts = [system_prefix]

            if loaded_additional_prompt_content:
                prompt_parts.append(
                    f"{loaded_additional_prompt_content}\n\n---\n\nUser Request:\n"
                )

            prompt_parts.append(query)
            final_query = "".join(prompt_parts)

            print(f"[DEBUG] Final combined query:\n{final_query}")

            # 4. mcp_client.process_query 호출 시 결합된 쿼리 사용
            ai_response = await self.mcp_client.process_query(
                final_query,
                file_paths=file_paths or [],
            )
            print(
                f"[DEBUG] Raw AI response received from client:\n---\n{ai_response}\n---"
            )

            self.response_queue.put(f"AI\n{ai_response}")

        except Exception as e:
            self.response_queue.put(f"System: AI 처리 중 오류 발생: {e}")
            traceback.print_exc()
        finally:
            self.attached_files.clear()
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

                    current_file_paths = list(self.attached_files)

                    asyncio.run_coroutine_threadsafe(
                        self._process_ai_query(
                            user_input,
                            additional_prompt,
                            file_paths=current_file_paths,
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

            self.attached_files.clear()
            self.is_first_request = True
            print("AppController: 새로운 채팅 세션 시작됨 (첫 요청 플래그 리셋).")
            return True
        except Exception as e:
            error_msg = f"새로운 채팅 세션을 시작하는 데 실패했습니다: {e}"
            print(f"AppController 오류: {error_msg}")
            traceback.print_exc()
            self.response_queue.put(f"System: 오류: {error_msg}")
            return False

    def process_user_request(self, user_request: str, additional_prompt: Optional[str]):
        """사용자 텍스트 요청 처리"""
        if not self.mcp_client:
            self.response_queue.put(
                "System: 오류: MCP 클라이언트가 준비되지 않았습니다."
            )
            self.response_queue.put("System: Buttons enabled")
            return

        self.response_queue.put(f"User\n{user_request}")

        current_file_paths = list(self.attached_files)

        asyncio.run_coroutine_threadsafe(
            self._process_ai_query(
                user_request,
                additional_prompt,
                file_paths=current_file_paths,
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

        additional_prompt_name = None
        if self.gui:
            try:
                additional_prompt_name = self.gui.prompt_dropdown.currentText()
                print(
                    f"[DEBUG] Selected prompt name from GUI: {additional_prompt_name}"
                )
            except AttributeError:
                print(
                    "AppController 경고: GUI에 prompt_dropdown이 없거나 currentText 메서드가 없습니다. 추가 프롬프트 이름 가져오기 실패."
                )
                additional_prompt_name = None
        else:
            print(
                "AppController 경고: handle_voice_input 호출 시 GUI가 설정되지 않음. 추가 프롬프트 이름 사용 불가."
            )
            additional_prompt_name = None

        threading.Thread(
            target=self._run_stt_in_thread,
            args=(additional_prompt_name,),
            daemon=True,
        ).start()

    def start_new_chat_session(self) -> bool:
        """새 채팅 세션 시작 요청 처리"""
        if self.gui:
            self.response_queue.put("System: Clear chat display")
        return self._start_new_chat()

    def attach_file(self, filepath: str):
        """파일 첨부 요청 처리"""
        if filepath not in self.attached_files:
            self.attached_files.append(filepath)
            filename = os.path.basename(filepath)
            print(
                f"AppController: 파일 첨부됨 - {filename} (총 {len(self.attached_files)}개)"
            )
            return True
        else:
            print(
                f"AppController: 이미 첨부된 파일입니다 - {os.path.basename(filepath)}"
            )
            return False

    def get_attachment_count(self) -> int:
        """현재 첨부된 파일의 개수를 반환합니다."""
        return len(self.attached_files)

    def get_attachment_paths(self) -> list[str]:
        """현재 첨부된 파일의 경로 리스트를 반환합니다."""
        return list(self.attached_files)

    def remove_attachment(self, filepath: str):
        """첨부 파일 목록에서 특정 파일을 제거합니다."""
        if filepath in self.attached_files:
            self.attached_files.remove(filepath)
            filename = os.path.basename(filepath)
            print(
                f"AppController: 파일 제거됨 - {filename} (남은 파일 {len(self.attached_files)}개)"
            )
            return True
        else:
            print(
                f"AppController: 제거하려는 파일이 목록에 없습니다 - {os.path.basename(filepath)}"
            )
            return False

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

        if self.hotkey_manager:
            print("AppController: HotkeyManager 리스너 종료 중...")
            self.hotkey_manager.stop_listener()
            print("AppController: HotkeyManager 리스너 종료 완료.")

        print("AppController: 정리 완료.")

    def process_user_request(self, user_request: str, additional_prompt: Optional[str]):
        """사용자 텍스트 요청 처리"""
        if not self.mcp_client:
            self.response_queue.put(
                "System: 오류: MCP 클라이언트가 준비되지 않았습니다."
            )
            self.response_queue.put("System: Buttons enabled")
            return

        self.response_queue.put(f"User\n{user_request}")

        current_file_paths = list(self.attached_files)

        asyncio.run_coroutine_threadsafe(
            self._process_ai_query(
                user_request,
                additional_prompt,
                file_paths=current_file_paths,
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

        additional_prompt_name = None
        if self.gui:
            try:
                additional_prompt_name = self.gui.prompt_dropdown.currentText()
                print(
                    f"[DEBUG] Selected prompt name from GUI: {additional_prompt_name}"
                )
            except AttributeError:
                print(
                    "AppController 경고: GUI에 prompt_dropdown이 없거나 currentText 메서드가 없습니다. 추가 프롬프트 이름 가져오기 실패."
                )
                additional_prompt_name = None
        else:
            print(
                "AppController 경고: handle_voice_input 호출 시 GUI가 설정되지 않음. 추가 프롬프트 이름 사용 불가."
            )
            additional_prompt_name = None

        threading.Thread(
            target=self._run_stt_in_thread,
            args=(additional_prompt_name,),
            daemon=True,
        ).start()

    def start_new_chat_session(self) -> bool:
        """새 채팅 세션 시작 요청 처리"""
        if self.gui:
            self.response_queue.put("System: Clear chat display")
        return self._start_new_chat()

    def attach_file(self, filepath: str):
        """파일 첨부 요청 처리"""
        if filepath not in self.attached_files:
            self.attached_files.append(filepath)
            filename = os.path.basename(filepath)
            print(
                f"AppController: 파일 첨부됨 - {filename} (총 {len(self.attached_files)}개)"
            )
            return True
        else:
            print(
                f"AppController: 이미 첨부된 파일입니다 - {os.path.basename(filepath)}"
            )
            return False

    def get_attachment_count(self) -> int:
        """현재 첨부된 파일의 개수를 반환합니다."""
        return len(self.attached_files)

    def get_attachment_paths(self) -> list[str]:
        """현재 첨부된 파일의 경로 리스트를 반환합니다."""
        return list(self.attached_files)

    def remove_attachment(self, filepath: str):
        """첨부 파일 목록에서 특정 파일을 제거합니다."""
        if filepath in self.attached_files:
            self.attached_files.remove(filepath)
            filename = os.path.basename(filepath)
            print(
                f"AppController: 파일 제거됨 - {filename} (남은 파일 {len(self.attached_files)}개)"
            )
            return True
        else:
            print(
                f"AppController: 제거하려는 파일이 목록에 없습니다 - {os.path.basename(filepath)}"
            )
            return False

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

        if self.hotkey_manager:
            print("AppController: HotkeyManager 리스너 종료 중...")
            self.hotkey_manager.stop_listener()
            print("AppController: HotkeyManager 리스너 종료 완료.")

        print("AppController: 정리 완료.")
