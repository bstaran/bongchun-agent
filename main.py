import os
import sys
import google.generativeai as genai
import json
import asyncio
import traceback
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import queue

from dotenv import load_dotenv
from client import MultiMCPClient

try:
    from stt_service import STTService
except ImportError:
    sys.exit(1)
except RuntimeError as e:
    print(f"STT 서비스 초기화 실패: {e}")
    sys.exit(1)


# --- 사용자 정의 프롬프트 파일 경로 (필요시 수정) ---
CUSTOM_PROMPT_FILE_PATH = "prompt/default.txt"

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


# --- GUI Application Class ---
class ChatGUI:
    def __init__(self, loop):
        self.loop = loop
        self.root = tk.Tk()
        self.root.title("AI Agent Chat")
        self.root.geometry("600x500")

        self.mcp_client = None
        self.stt_service = None
        self.response_queue = queue.Queue()  # 비동기 결과 전달용 큐

        self._setup_system_instruction()
        self._initialize_services()
        self._create_widgets()
        self._check_queue()  # 큐 폴링 시작

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)  # 종료 시 처리

        # MCP 서버 연결 (백그라운드)
        if self.mcp_client:
            print("\nMCP 서버 연결 시도 중 (백그라운드)...")
            asyncio.run_coroutine_threadsafe(self._connect_mcp_servers(), self.loop)

    def _setup_system_instruction(self):
        self.system_instruction = ""
        if CUSTOM_PROMPT_FILE_PATH:
            try:
                with open(CUSTOM_PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
                    self.system_instruction = f.read()
                print(f"'{CUSTOM_PROMPT_FILE_PATH}'에서 시스템 프롬프트 로드됨.")
            except FileNotFoundError:
                print(f"경고: 프롬프트 파일 '{CUSTOM_PROMPT_FILE_PATH}' 없음.")
            except Exception as e:
                print(f"경고: 프롬프트 파일 읽기 실패 - {e}.")

    def _initialize_services(self):
        """MCP 클라이언트와 STT 서비스 초기화"""
        try:
            # STT 서비스 초기화 시도 (ImportError 또는 RuntimeError 발생 가능)
            try:
                self.stt_service = STTService(
                    model_name=whisper_model_name,
                    device_preference=whisper_device_pref,
                )
                print("STT 서비스 초기화 완료.")
            except NameError:  # STTService import 실패 시
                print(
                    "경고: STTService를 import할 수 없어 음성 입력 기능이 비활성화됩니다."
                )
                self.stt_service = None
            except RuntimeError as e:
                print(
                    f"경고: STT 서비스 초기화 실패 ({e}). 음성 입력 기능이 비활성화됩니다."
                )
                self.stt_service = None

            self.mcp_client = MultiMCPClient(
                model_name=model_name,
                safety_settings=safety_settings,
                generation_config=generation_config,
                system_instruction=self.system_instruction,
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
                self.response_queue.put(f"System: 사용 가능한 MCP 도구: {tool_names}")
        except Exception as e:
            print(f"MCP 서버 연결 오류: {e}")
            self.response_queue.put(f"System: 오류: MCP 서버 연결 실패 - {e}")
            traceback.print_exc()

    def _create_widgets(self):
        """GUI 위젯 생성 및 배치"""
        # 프롬프트 입력 영역
        prompt_frame = tk.Frame(self.root)
        prompt_frame.pack(pady=10, padx=10, fill=tk.X)

        prompt_label = tk.Label(prompt_frame, text="Prompt:")
        prompt_label.pack(side=tk.LEFT, padx=5)

        self.prompt_entry = scrolledtext.ScrolledText(
            prompt_frame, height=4, wrap=tk.WORD
        )
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.prompt_entry.focus()
        # Enter 키 바인딩 추가
        self.prompt_entry.bind("<Return>", self._send_prompt_handler)
        self.prompt_entry.bind("<Shift-Return>", self._insert_newline)

        # 버튼 프레임
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5, padx=10)

        # 전송 버튼
        self.send_button = tk.Button(
            button_frame, text="Send", command=self._send_prompt_handler
        )
        self.send_button.pack(side=tk.LEFT, padx=5)

        # 음성 입력 버튼 (STT 서비스가 있을 경우)
        if self.stt_service:
            self.stt_button = tk.Button(
                button_frame, text="Voice Input", command=self._voice_input_handler
            )
            self.stt_button.pack(side=tk.LEFT, padx=5)
        else:
            self.stt_button = None  # 명시적으로 None 설정

        # 답변 출력 영역
        response_label = tk.Label(self.root, text="Response:")
        response_label.pack(pady=(10, 0), padx=10, anchor=tk.W)

        self.response_area = scrolledtext.ScrolledText(
            self.root, height=15, wrap=tk.WORD, state=tk.DISABLED
        )
        self.response_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- 단축키 바인딩 ---
        # 음성 입력 시작 단축키 (Shift+Control+Option+Command+T)
        # macOS Tkinter 표현 시도
        self.root.bind(
            "<Shift-Control-Option-Command-T>", self._voice_input_handler_wrapper
        )

    def _insert_newline(self, event):
        """Shift+Enter 입력 시 줄바꿈 삽입"""
        self.prompt_entry.insert(tk.INSERT, "\n")
        return "break"  # 기본 Enter 동작 방지

    def _send_prompt_handler(self, event=None):  # event 인자 추가
        """전송 버튼 클릭 또는 Enter 키 입력 시 호출될 핸들러"""
        prompt_text = self.prompt_entry.get("1.0", tk.END).strip()
        if not prompt_text:
            # messagebox.showwarning("입력 오류", "프롬프트를 입력하세요.") # 비어있는 입력은 무시
            return "break"  # Enter 키 이벤트 전파 중지

        if not self.mcp_client:
            messagebox.showerror("오류", "MCP 클라이언트가 준비되지 않았습니다.")
            return "break"
        # 서버 연결 상태 확인 추가
        if not self.mcp_client.sessions:
            messagebox.showwarning(
                "연결 오류", "연결된 MCP 서버가 없습니다. 텍스트 생성만 가능합니다."
            )
            # 서버 없이도 텍스트 생성은 가능하도록 할 수 있음 (선택적)
            # return "break" # 또는 여기서 중단

        self._display_response(f"You: {prompt_text}")  # 사용자 입력 표시
        self.prompt_entry.delete("1.0", tk.END)  # 입력 필드 초기화
        self._disable_buttons()  # 버튼 비활성화

        # 비동기 작업 호출
        asyncio.run_coroutine_threadsafe(self._process_ai_query(prompt_text), self.loop)
        return "break"  # Enter 키 이벤트 전파 중지 (Text 위젯의 기본 동작 방지)

    def _voice_input_handler(self):
        """음성 입력 버튼 클릭 시 호출될 핸들러"""
        if not self.stt_service:
            messagebox.showerror(
                "오류", "STT 서비스가 초기화되지 않았거나 사용할 수 없습니다."
            )
            return

        self._display_response("System: 음성 입력을 시작합니다...")
        self._disable_buttons()

        # STT 작업을 별도 스레드에서 실행 (Tkinter GUI 블로킹 방지)
        threading.Thread(target=self._run_stt_in_thread, daemon=True).start()

    def _run_stt_in_thread(self):
        """STT 작업을 별도 스레드에서 실행"""
        try:
            audio_data = self.stt_service.record_audio()  # 동기 호출
            # NumPy 배열의 존재 및 내용 확인 (None이 아니고 size가 0보다 큰지)
            if audio_data is not None and audio_data.size > 0:
                user_input = self.stt_service.transcribe_audio(audio_data)  # 동기 호출
                if user_input:
                    self.response_queue.put(f"Voice Input Recognized: {user_input}")
                    # 인식된 텍스트로 AI 쿼리 실행
                    asyncio.run_coroutine_threadsafe(
                        self._process_ai_query(user_input), self.loop
                    )
                else:
                    self.response_queue.put("System: 음성을 인식하지 못했습니다.")
                    self.response_queue.put(
                        "System: Buttons enabled"
                    )  # 버튼 다시 활성화
            else:
                self.response_queue.put("System: 오디오 녹음 실패.")
                self.response_queue.put("System: Buttons enabled")  # 버튼 다시 활성화
        except Exception as e:
            self.response_queue.put(f"System: 음성 입력 중 오류: {e}")
            traceback.print_exc()
            self.response_queue.put("System: Buttons enabled")  # 버튼 다시 활성화

    def _voice_input_handler_wrapper(self, event=None):
        """단축키 이벤트를 처리하고 음성 입력 핸들러 호출"""
        # 버튼이 활성화 상태일 때만 음성 입력 실행
        if (
            self.stt_service
            and self.stt_button
            and self.stt_button["state"] == tk.NORMAL
        ):
            self._voice_input_handler()
        else:
            # 음성 입력 비활성화 시 사용자에게 알림 (선택 사항)
            # self._display_response("System: 음성 입력 기능이 비활성화되어 있거나 사용할 수 없습니다.")
            print("음성 입력 단축키: STT 서비스 비활성화 또는 버튼 비활성 상태")
        return "break"  # 이벤트 전파 중지

    async def _process_ai_query(self, query):
        """비동기로 AI 쿼리 처리"""
        try:
            self.response_queue.put("System: AI 처리 중...")
            ai_response = await self.mcp_client.process_query(query)
            self.response_queue.put(f"AI: {ai_response}")
        except Exception as e:
            self.response_queue.put(f"System: AI 처리 중 오류 발생: {e}")
            traceback.print_exc()
        finally:
            # 작업 완료 후 버튼 활성화 (큐를 통해 전달)
            self.response_queue.put("System: Buttons enabled")

    def _display_response(self, text):
        """답변 영역에 텍스트 표시"""
        self.response_area.config(state=tk.NORMAL)
        self.response_area.insert(tk.END, text + "\n\n")
        self.response_area.see(tk.END)  # 스크롤 맨 아래로 이동
        self.response_area.config(state=tk.DISABLED)

    def _check_queue(self):
        """큐를 주기적으로 확인하여 GUI 업데이트"""
        try:
            while True:
                message = self.response_queue.get_nowait()
                if message == "System: Buttons enabled":
                    self._enable_buttons()
                else:
                    self._display_response(message)
        except queue.Empty:
            pass
        finally:
            # 100ms 마다 큐 다시 확인
            self.root.after(100, self._check_queue)

    def _disable_buttons(self):
        """입력 버튼 비활성화"""
        self.send_button.config(state=tk.DISABLED)
        if self.stt_button:
            self.stt_button.config(state=tk.DISABLED)

    def _enable_buttons(self):
        """입력 버튼 활성화"""
        self.send_button.config(state=tk.NORMAL)
        if self.stt_button:
            self.stt_button.config(state=tk.NORMAL)

    def _on_closing(self):
        """창 닫기 버튼 클릭 시 호출될 함수"""
        if messagebox.askokcancel("종료 확인", "애플리케이션을 종료하시겠습니까?"):
            print("애플리케이션 종료 시작...")
            # 비동기 클린업 작업 실행 요청
            if self.mcp_client:
                # loop가 실행 중일 때만 안전하게 호출
                if self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.mcp_client.cleanup(), self.loop
                    )
                else:
                    print(
                        "경고: 이벤트 루프가 실행 중이 아니므로 MCP 클린업을 건너<0xEB><0x9C><0x84>니다."
                    )

            if self.stt_service:
                self.stt_service.stop_recording()  # STT 중지

            # 이벤트 루프 중지 요청 (별도 스레드에서 실행 중인 경우)
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)

            self.root.destroy()
            print("GUI 종료 완료.")

    def run(self):
        """GUI 메인 루프 시작"""
        self.root.mainloop()


# --- 비동기 루프를 실행할 스레드 ---
def run_async_loop(loop):
    asyncio.set_event_loop(loop)  # 현재 스레드의 이벤트 루프로 설정
    try:
        print("비동기 이벤트 루프 시작...")
        loop.run_forever()
    finally:
        print("비동기 이벤트 루프 종료 중...")
        # 루프 종료 시 남은 작업 처리 (이미 stop()이 호출되었으므로 추가 실행 필요 없을 수 있음)
        # tasks = asyncio.all_tasks(loop)
        # for task in tasks:
        #     task.cancel()
        # loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        if not loop.is_closed():
            loop.close()
        print("비동기 이벤트 루프 종료 완료.")


# --- 메인 실행 부분 ---
if __name__ == "__main__":
    # 별도의 스레드에서 실행될 asyncio 이벤트 루프 생성
    async_loop = asyncio.new_event_loop()

    # 비동기 루프를 실행할 스레드 시작
    loop_thread = threading.Thread(
        target=run_async_loop, args=(async_loop,), daemon=True
    )
    loop_thread.start()

    # 메인 스레드에서 Tkinter GUI 실행
    app = None  # app 변수 초기화
    try:
        # GUI 생성 시 루프 전달
        app = ChatGUI(async_loop)
        app.run()  # Tkinter 메인 루프 시작 (메인 스레드 블로킹)
    except Exception as e:
        print(f"\nGUI 실행 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        # GUI가 종료되면 비동기 루프도 확실히 종료되도록 시도
        if async_loop.is_running():
            print("메인 스레드: 비동기 루프에 종료 요청...")
            async_loop.call_soon_threadsafe(async_loop.stop)

        # 스레드가 완전히 종료될 때까지 기다릴 수 있음 (선택적, 데몬 스레드이므로 주 스레드 종료 시 자동 종료됨)
        # loop_thread.join(timeout=5) # 5초 타임아웃
        # if loop_thread.is_alive():
        #     print("경고: 비동기 루프 스레드가 시간 내에 종료되지 않았습니다.")

        print("메인 스레드 종료.")
