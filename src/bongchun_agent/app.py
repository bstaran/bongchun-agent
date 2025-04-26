import os
import sys
import google.generativeai as genai
import json
import asyncio
import traceback
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import threading
import queue
import platform

try:
    from pynput import keyboard
except ImportError:
    print(
        "오류: pynput 라이브러리를 찾을 수 없습니다. 시스템 전역 단축키 기능이 비활성화됩니다."
    )
    print("다음 명령어를 실행하여 설치하세요: uv add pynput")
    keyboard = None

from dotenv import load_dotenv
from bongchun_agent.client import MultiMCPClient

try:
    from bongchun_agent.stt_service import STTService
except ImportError:
    sys.exit(1)
except RuntimeError as e:
    print(f"STT 서비스 초기화 실패: {e}")
    sys.exit(1)


# CLI 인자 파싱 함수 제거됨

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

    # --- STT Provider 설정 ---
    stt_provider = os.getenv("STT_PROVIDER", "whisper").lower()
    if stt_provider not in ["whisper", "google"]:
        print(
            f"경고: STT_PROVIDER 환경 변수 값 '{stt_provider}'이(가) 유효하지 않습니다. 'whisper' 설정을 사용합니다."
        )
        stt_provider = "whisper"
    print(f"사용할 STT 제공자: '{stt_provider}'")

    # Google Cloud STT 사용 시 인증 정보 확인
    google_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if stt_provider == "google" and not google_credentials:
        print(
            "\n경고: STT_PROVIDER가 'google'로 설정되었지만 GOOGLE_APPLICATION_CREDENTIALS 환경 변수가 설정되지 않았습니다."
        )
        print("Google Cloud 인증에 실패할 수 있습니다. .env 파일을 확인하세요.\n")
    elif stt_provider == "google" and google_credentials:
        if not os.path.exists(google_credentials):
            print(
                f"\n경고: GOOGLE_APPLICATION_CREDENTIALS 경로 '{google_credentials}'에 파일이 존재하지 않습니다."
            )
            print("Google Cloud 인증에 실패할 수 있습니다.\n")
        else:
            print(f"Google Cloud 인증 파일 경로: '{google_credentials}'")


except (ValueError, FileNotFoundError) as e:
    print(f"오류: 설정 로드 실패 - {e}")
    sys.exit(1)
except Exception as e:
    print(f"설정 중 예기치 않은 오류 발생: {e}")
    traceback.print_exc()
    sys.exit(1)


# --- GUI Application Class ---
class ChatGUI:
    def __init__(self, loop):
        self.loop = loop
        self.root = tk.Tk()
        self.root.title("AI Agent Chat")
        self.root.geometry("600x550")

        self.mcp_client = None
        self.stt_service = None
        self.response_queue = queue.Queue()
        self.hotkey_listener = None
        self.recording_status_label = None

        # --- 프롬프트 관련 변수 ---
        self.prompt_dir = "prompt"
        self.available_prompts = self._load_prompts()
        self.prompt_var = tk.StringVar(self.root)
        self.selected_prompt_content = ""
        self.default_prompt_path = os.path.join(self.prompt_dir, "default.txt")

        # --- 서비스 초기화 ---
        self._initialize_services()
        self._create_widgets()
        self._check_queue()

        # 초기 프롬프트 로드
        if self.available_prompts:
            self.prompt_var.set(self.available_prompts[0])
            self._load_selected_prompt_content()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        if self.mcp_client:
            print("\nMCP 서버 연결 시도 중 (백그라운드)...")
            asyncio.run_coroutine_threadsafe(self._connect_mcp_servers(), self.loop)

    # --- 프롬프트 로딩 관련 메서드 ---
    def _load_prompts(self):
        """Loads .txt file names (without extension) from the prompt directory."""
        prompts = []
        if os.path.isdir(self.prompt_dir):
            try:
                for filename in os.listdir(self.prompt_dir):
                    if filename.endswith(".txt"):
                        prompts.append(os.path.splitext(filename)[0])
            except OSError as e:
                messagebox.showerror("Error", f"Could not read prompt directory: {e}")

        if "default" not in prompts and os.path.exists(self.default_prompt_path):
            prompts.insert(0, "default")
        elif not prompts and not os.path.exists(self.default_prompt_path):
            messagebox.showwarning(
                "Warning", "No prompts found, including default.txt."
            )
            return ["default"]

        if "default" in prompts:
            prompts.remove("default")
            prompts.insert(0, "default")
        return prompts if prompts else ["default"]

    def _load_selected_prompt_content(self):
        """Loads the content of the currently selected prompt file."""
        selected_prompt_name = self.prompt_var.get()
        prompt_file_path = os.path.join(self.prompt_dir, f"{selected_prompt_name}.txt")

        try:
            if os.path.exists(prompt_file_path):
                with open(prompt_file_path, "r", encoding="utf-8") as f:
                    self.selected_prompt_content = f.read()
                print(f"Loaded prompt content from: {prompt_file_path}")
            elif os.path.exists(self.default_prompt_path):
                messagebox.showwarning(
                    "Warning",
                    f"Prompt '{selected_prompt_name}.txt' not found. Using default prompt.",
                )
                with open(self.default_prompt_path, "r", encoding="utf-8") as f:
                    self.selected_prompt_content = f.read()
                self.prompt_var.set("default")
                print(f"Loaded default prompt content from: {self.default_prompt_path}")
            else:
                messagebox.showerror("Error", "Default prompt 'default.txt' not found.")
                self.selected_prompt_content = ""
        except OSError as e:
            messagebox.showerror("Error", f"Could not read prompt file: {e}")
            self.selected_prompt_content = ""
        except Exception as e:
            messagebox.showerror(
                "Error", f"An unexpected error occurred reading prompt: {e}"
            )
            self.selected_prompt_content = ""

    def _on_prompt_select(self, event=None):
        """Callback when a prompt is selected from the dropdown."""
        self._load_selected_prompt_content()
        self.root.title(f"AI Agent Chat (Prompt: {self.prompt_var.get()})")

    def _initialize_services(self):
        """MCP 클라이언트와 STT 서비스 초기화"""

        try:
            try:
                print(f"STT 서비스 초기화 시도 (제공자: {stt_provider})...")
                self.stt_service = STTService(
                    provider=stt_provider,
                    whisper_model_name=whisper_model_name,
                    whisper_device_preference=whisper_device_pref,
                )
                print(f"STT 서비스 ({stt_provider}) 초기화 완료.")
            except NameError:
                print(
                    "오류: STTService 클래스를 import할 수 없습니다. stt_service.py 파일을 확인하세요."
                )
                self.stt_service = None
            except ImportError as ie:
                print(
                    f"오류: STT 서비스 의존성 로드 실패 ({ie}). 음성 입력 기능이 비활성화됩니다."
                )
                self.stt_service = None
            except RuntimeError as e:
                print(
                    f"경고: STT 서비스 ({stt_provider}) 초기화 실패 ({e}). 음성 입력 기능이 비활성화됩니다."
                )
                self.stt_service = None

            self.mcp_client = MultiMCPClient(
                model_name=model_name,
                safety_settings=safety_settings,
                generation_config=generation_config,
                system_instruction=None,
            )
            print("MCP 클라이언트 초기화 완료.")

        except Exception as e:
            messagebox.showerror("초기화 오류", f"서비스 초기화 중 오류: {e}")
            traceback.print_exc()
            self.root.quit()

    async def _connect_mcp_servers(self):
        """비동기 MCP 서버 연결"""
        try:
            await self.mcp_client.connect_all_servers(mcp_servers)
            if not self.mcp_client.sessions:
                print("경고: 연결된 MCP 서버가 없습니다.")
                self.response_queue.put(
                    "System: 경고: 연결된 MCP 서버가 없습니다. 도구 사용이 제한됩니다."
                )
            else:
                tool_names = [t.name for t in self.mcp_client.all_mcp_tools]
                print(f"사용 가능한 MCP 도구 ({len(tool_names)}개): {tool_names}")
        except Exception as e:
            print(f"MCP 서버 연결 오류: {e}")
            self.response_queue.put(f"System: 오류: MCP 서버 연결 실패 - {e}")
            traceback.print_exc()

    def _create_widgets(self):
        """GUI 위젯 생성 및 배치"""

        prompt_select_frame = tk.Frame(self.root)
        prompt_select_frame.pack(pady=(10, 5), padx=10, fill=tk.X)

        prompt_select_label = tk.Label(prompt_select_frame, text="Select Prompt:")
        prompt_select_label.pack(side=tk.LEFT, padx=(0, 5))

        self.prompt_dropdown = ttk.Combobox(
            prompt_select_frame,
            textvariable=self.prompt_var,
            values=self.available_prompts,
            state="readonly",
            width=30,
        )
        if self.available_prompts:
            self.prompt_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.prompt_dropdown.bind("<<ComboboxSelected>>", self._on_prompt_select)
        else:
            no_prompt_label = tk.Label(
                prompt_select_frame,
                text="No prompts found in 'prompt' directory.",
                fg="grey",
            )
            no_prompt_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- 사용자 요청 입력 프레임 ---
        request_frame = tk.Frame(self.root)
        request_frame.pack(pady=5, padx=10, fill=tk.X)

        request_label = tk.Label(request_frame, text="Your Request:")
        request_label.pack(side=tk.LEFT, padx=5, anchor=tk.N)

        self.request_entry = scrolledtext.ScrolledText(
            request_frame, height=6, wrap=tk.WORD
        )
        self.request_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.request_entry.focus()
        self.request_entry.bind("<Return>", self._send_prompt_handler)
        self.request_entry.bind("<Shift-Return>", self._insert_newline)

        # --- 버튼 프레임 ---
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5, padx=10)

        # 전송 버튼
        self.send_button = tk.Button(
            button_frame, text="Send", command=self._send_prompt_handler
        )
        self.send_button.pack(side=tk.LEFT, padx=5)

        # 새 채팅 시작 버튼
        self.new_chat_button = tk.Button(
            button_frame, text="새 채팅 시작", command=self._start_new_chat_handler
        )
        self.new_chat_button.pack(side=tk.LEFT, padx=5)

        # 음성 입력 버튼 (STT 서비스가 있을 경우)
        if self.stt_service:
            self.stt_button = tk.Button(
                button_frame, text="Voice Input", command=self._voice_input_handler
            )
            self.stt_button.pack(side=tk.LEFT, padx=5)
        else:
            self.stt_button = None

        # 답변 출력 영역
        response_label = tk.Label(self.root, text="Response:")
        response_label.pack(pady=(10, 0), padx=10, anchor=tk.W)

        self.response_area = scrolledtext.ScrolledText(
            self.root, height=15, wrap=tk.WORD, state=tk.DISABLED
        )
        self.response_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.response_area.tag_configure("user_message", justify="right")
        self.response_area.tag_configure("ai_message", justify="left")

        self.recording_status_label = tk.Label(
            self.root, text="", fg="red", font=("Helvetica", 10)
        )
        self.recording_status_label.pack_forget()

    def _insert_newline(self, event):
        """Shift+Enter 입력 시 줄바꿈 삽입 (request_entry에 적용)"""
        self.request_entry.insert(tk.INSERT, "\n")
        return "break"

    def _send_prompt_handler(self, event=None):
        """전송 버튼 클릭 또는 Enter 키 입력 시 호출될 핸들러"""
        user_request = self.request_entry.get("1.0", tk.END).strip()
        if not user_request:
            messagebox.showwarning("Input Error", "Please enter your request.")
            return "break"

        if not self.selected_prompt_content:
            self._load_selected_prompt_content()
            if not self.selected_prompt_content:
                messagebox.showerror(
                    "Error",
                    "Cannot send request without prompt content (default.txt missing?).",
                )
                return "break"

        if not self.mcp_client:
            messagebox.showerror("오류", "MCP 클라이언트가 준비되지 않았습니다.")
            return "break"

        if not self.mcp_client.sessions:
            messagebox.showwarning(
                "연결 오류", "연결된 MCP 서버가 없습니다. 텍스트 생성만 가능합니다."
            )

        self._display_response(f"You: {user_request}")
        self.request_entry.delete("1.0", tk.END)
        self._disable_buttons()

        asyncio.run_coroutine_threadsafe(
            self._process_ai_query(user_request, self.selected_prompt_content),
            self.loop,
        )
        return "break"

    def _voice_input_handler(self):
        """음성 입력 버튼 클릭 시 호출될 핸들러"""
        if not self.stt_service:
            messagebox.showerror(
                "오류", "STT 서비스가 초기화되지 않았거나 사용할 수 없습니다."
            )
            return

        if self.recording_status_label:
            self.recording_status_label.config(text="🔴 녹음 중...")
            self.recording_status_label.pack(pady=(0, 5), padx=10, anchor=tk.W)
            self.recording_status_label.lift()
        self._disable_buttons()

        threading.Thread(target=self._run_stt_in_thread, daemon=True).start()

    def _run_stt_in_thread(self):
        """STT 작업을 별도 스레드에서 실행"""
        try:
            audio_data = self.stt_service.record_audio()
            if audio_data is not None and audio_data.size > 0:
                user_input = self.stt_service.transcribe_audio(audio_data)
                if user_input:
                    self.response_queue.put(f"Voice Input Recognized: {user_input}")
                    asyncio.run_coroutine_threadsafe(
                        self._process_ai_query(user_input), self.loop
                    )
                else:
                    self.response_queue.put("System: 음성을 인식하지 못했습니다.")
                    self.response_queue.put("System: Buttons enabled")
            else:
                self.response_queue.put("System: 오디오 녹음 실패.")
                self.response_queue.put("System: Buttons enabled")
        except Exception as e:
            self.response_queue.put(f"System: 음성 입력 중 오류: {e}")
            traceback.print_exc()
        finally:
            self.response_queue.put("System: Buttons enabled")
            self.response_queue.put("System: Hide recording status")

    def _voice_input_handler_wrapper(self, event=None):
        """단축키 이벤트를 처리하고 음성 입력 핸들러 호출"""
        print(f"단축키 핸들러 호출됨 (이벤트: {event})")
        if (
            self.stt_service
            and self.stt_button
            and self.stt_button["state"] == tk.NORMAL
        ):
            self._voice_input_handler()
        else:
            print("음성 입력 단축키: STT 서비스 비활성화 또는 버튼 비활성 상태")
        return "break"

    def _start_new_chat(self):
        """새로운 채팅 세션을 시작하고 GUI를 초기화합니다."""
        if not self.mcp_client or not self.mcp_client.gemini_model:
            messagebox.showerror(
                "오류", "MCP 클라이언트 또는 Gemini 모델이 초기화되지 않았습니다."
            )
            return False

        try:
            self.mcp_client.chat_session = self.mcp_client.gemini_model.start_chat(
                enable_automatic_function_calling=True
            )
            self.response_area.config(state=tk.NORMAL)
            self.response_area.delete("1.0", tk.END)
            self.response_area.config(state=tk.DISABLED)
            print("새로운 채팅 세션 시작됨.")
            return True
        except Exception as e:
            error_msg = f"새로운 채팅 세션을 시작하는 데 실패했습니다: {e}"
            print(f"오류: {error_msg}")
            traceback.print_exc()
            messagebox.showerror("오류", error_msg)
            return False

    def _start_new_chat_handler(self):
        """새 채팅 시작 버튼 클릭 시 호출될 핸들러"""
        print("새 채팅 시작 버튼 클릭됨")
        self._start_new_chat()

    async def _process_ai_query(self, query, prompt_content):
        """비동기로 AI 쿼리 처리 (프롬프트 내용 포함)"""
        try:
            self.response_queue.put("System: AI 처리 중...")
            ai_response = await self.mcp_client.process_query(
                query, prompt_content=prompt_content
            )
            self.response_queue.put(f"AI: {ai_response}")
        except Exception as e:
            self.response_queue.put(f"System: AI 처리 중 오류 발생: {e}")
            traceback.print_exc()
        finally:
            self.response_queue.put("System: Buttons enabled")

    def _display_response(self, text):
        """답변 영역에 텍스트 표시 (정렬 포함)"""
        self.response_area.config(state=tk.NORMAL)
        start_index = self.response_area.index(tk.END + "-1c")
        self.response_area.insert(tk.END, text + "\n\n")
        end_index = self.response_area.index(tk.END + "-1c")

        if text.startswith("You:"):
            self.response_area.tag_add("user_message", start_index, end_index)
        elif text.startswith("AI:"):
            self.response_area.tag_add("ai_message", start_index, end_index)

        self.response_area.see(tk.END)
        self.response_area.config(state=tk.DISABLED)

    def _check_queue(self):
        """큐를 주기적으로 확인하여 GUI 업데이트"""
        try:
            while True:
                message = self.response_queue.get_nowait()
                if message == "System: Buttons enabled":
                    self._enable_buttons()
                elif message == "System: Hide recording status":
                    if self.recording_status_label:
                        self.recording_status_label.pack_forget()
                elif isinstance(message, str) and not message.startswith("System:"):
                    self._display_response(message)
                elif isinstance(message, str):
                    print(message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._check_queue)

    def _disable_buttons(self):
        """입력 버튼 비활성화"""
        self.send_button.config(state=tk.DISABLED)
        if self.stt_button:
            self.stt_button.config(state=tk.DISABLED)
        self.new_chat_button.config(state=tk.DISABLED)

    def _enable_buttons(self):
        """입력 버튼 활성화"""
        self.send_button.config(state=tk.NORMAL)
        if self.stt_button:
            self.stt_button.config(state=tk.NORMAL)
        self.new_chat_button.config(state=tk.NORMAL)

    def _on_closing(self):
        """창 닫기 버튼 클릭 시 호출될 함수"""
        if messagebox.askokcancel("종료 확인", "애플리케이션을 종료하시겠습니까?"):
            print("애플리케이션 종료 시작...")
            if self.mcp_client:
                if self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.mcp_client.cleanup(), self.loop
                    )

            if self.stt_service:
                self.stt_service.stop_recording()

            if self.hotkey_listener:
                print("단축키 리스너 종료 중...")
                self.hotkey_listener.stop()
                print("단축키 리스너 종료 완료.")

            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)

            self.root.destroy()
            print("GUI 종료 완료.")

    def run(self):
        """GUI 메인 루프 시작"""
        self.root.mainloop()


# --- 비동기 루프를 실행할 스레드 ---
def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    try:
        print("비동기 이벤트 루프 시작...")
        loop.run_forever()
    finally:
        print("비동기 이벤트 루프 종료 중...")
        if not loop.is_closed():
            loop.close()
        print("비동기 이벤트 루프 종료 완료.")


# --- 단축키 콜백 함수 ---
def on_activate_voice_input(app_instance):
    """단축키 활성화 시 호출될 콜백"""
    print("전역 단축키 감지됨!")
    if app_instance:
        try:
            app_instance.root.after(0, app_instance._voice_input_handler_wrapper)
            print("메인 스레드에서 _voice_input_handler_wrapper 실행 예약됨.")
        except Exception as e:
            print(f"단축키 콜백에서 핸들러 호출 중 오류: {e}")
            traceback.print_exc()
    else:
        print("오류: ChatGUI 인스턴스가 없어 콜백을 실행할 수 없습니다.")


# --- GUI 실행 함수 ---
def run_gui(args):
    """GUI 애플리케이션을 초기화하고 실행합니다."""
    async_loop = asyncio.new_event_loop()

    loop_thread = threading.Thread(
        target=run_async_loop, args=(async_loop,), daemon=True
    )
    loop_thread.start()

    app = None
    try:
        app = ChatGUI(async_loop)

        # --- 시스템 전역 단축키 리스너 설정 ---
        if keyboard:
            shortcut_combination = "<cmd>+<ctrl>+<shift>+t"
            if platform.system() != "Darwin":
                print(
                    "경고: macOS가 아닌 환경입니다. 단축키 조합을 확인/조정해야 할 수 있습니다."
                )
                shortcut_combination = "<ctrl>+<alt>+<shift>+t"

            def create_callback(app_instance):
                return lambda: on_activate_voice_input(app_instance)

            hotkey_map = {shortcut_combination: create_callback(app)}

            try:
                hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
                hotkey_listener.start()
                app.hotkey_listener = hotkey_listener
                print(f"시스템 전역 단축키 리스너 시작됨 ({shortcut_combination})")
            except Exception as e:
                print(f"오류: 전역 단축키 리스너 시작 실패 - {e}")
                traceback.print_exc()
        else:
            print("pynput 라이브러리가 없어 전역 단축키 기능을 시작할 수 없습니다.")

        app.run()

    except Exception as e:
        print(f"\nGUI 실행 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        if async_loop.is_running():
            print("GUI 종료: 비동기 루프에 종료 요청...")
            async_loop.call_soon_threadsafe(async_loop.stop)

        print("run_gui 함수 종료.")


if __name__ == "__main__":
    print("app.py 직접 실행됨. GUI 시작...")
    run_gui(None)
