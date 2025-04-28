import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
import queue
from typing import Optional
import os

from .app_config import NO_PROMPT_OPTION

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app_controller import AppController


class ChatGUI:
    def __init__(self, controller: "AppController"):
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("AI Agent Chat")
        self.root.geometry("600x550")
        self.response_queue = self.controller.response_queue
        self.recording_status_label: Optional[tk.Label] = None
        self.attached_file_label: Optional[tk.Label] = None
        self.prompt_var = tk.StringVar(self.root)

        self._create_widgets()
        self._check_queue()

        if self.controller.prompt_manager.available_prompts:
            self.prompt_var.set(self.controller.prompt_manager.available_prompts[0])
            self._on_prompt_select()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_prompt_select(self, event=None):
        """Callback when a prompt is selected from the dropdown."""
        selected_display = self.prompt_var.get()
        if selected_display == NO_PROMPT_OPTION:
            self.root.title("AI Agent Chat (Prompt: None)")
        else:
            self.root.title(f"AI Agent Chat (Prompt: {selected_display})")

    def _create_widgets(self):
        """GUI 위젯 생성 및 배치"""
        prompt_select_frame = tk.Frame(self.root)
        prompt_select_frame.pack(pady=(10, 5), padx=10, fill=tk.X)

        prompt_select_label = tk.Label(
            prompt_select_frame, text="Select Additional Prompt:"
        )
        prompt_select_label.pack(side=tk.LEFT, padx=(0, 5))

        self.prompt_dropdown = ttk.Combobox(
            prompt_select_frame,
            textvariable=self.prompt_var,
            values=self.controller.prompt_manager.available_prompts,
            state="readonly",
            width=30,
        )
        self.prompt_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.prompt_dropdown.bind("<<ComboboxSelected>>", self._on_prompt_select)

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

        if self.controller.stt_service:
            self.stt_button = tk.Button(
                button_frame, text="Voice Input", command=self._voice_input_handler
            )
            self.stt_button.pack(side=tk.LEFT, padx=5)
        else:
            self.stt_button = None

        # 파일 첨부 버튼
        self.attach_button = tk.Button(
            button_frame, text="파일 첨부", command=self._attach_file_handler
        )
        self.attach_button.pack(side=tk.LEFT, padx=5)

        # 답변 출력 영역
        response_label = tk.Label(self.root, text="Response:")
        response_label.pack(pady=(10, 0), padx=10, anchor=tk.W)

        self.response_area = scrolledtext.ScrolledText(
            self.root, height=15, wrap=tk.WORD, state=tk.DISABLED
        )
        self.response_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.response_area.tag_configure("user_message", justify="right")
        self.response_area.tag_configure(
            "ai_message", justify="left", foreground="blue"
        )

        self.recording_status_label = tk.Label(
            self.root, text="", fg="red", font=("Helvetica", 10)
        )
        self.recording_status_label.pack_forget()

        # 첨부 파일 표시 레이블
        self.attached_file_label = tk.Label(
            self.root, text="", fg="blue", font=("Helvetica", 9)
        )
        self.attached_file_label.pack(pady=(0, 5), padx=10, anchor=tk.W)

    def _insert_newline(self, event):
        """Shift+Enter 입력 시 줄바꿈 삽입 (request_entry에 적용)"""
        self.request_entry.insert(tk.INSERT, "\n")
        return "break"

    def _send_prompt_handler(self, event=None):
        """전송 버튼 클릭 또는 Enter 키 입력 시 호출될 핸들러"""
        user_request = self.request_entry.get("1.0", tk.END).strip()
        if not user_request:
            messagebox.showwarning("입력 오류", "요청 내용을 입력해주세요.")
            return "break"

        # self._display_response(f"You: {user_request}") # 컨트롤러에서 큐를 통해 보내므로 GUI에서 직접 표시하지 않음
        self.request_entry.delete("1.0", tk.END)
        self._disable_buttons()

        additional_prompt = self.controller.prompt_manager.load_selected_prompt(
            self.prompt_var.get()
        )

        self.controller.process_user_request(user_request, additional_prompt)
        return "break"

    def _attach_file_handler(self):
        """파일 첨부 버튼 클릭 시 호출될 핸들러"""
        filetypes = (
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
            ("All files", "*.*"),
        )
        filepath = filedialog.askopenfilename(
            title="이미지 파일 선택", filetypes=filetypes
        )
        if filepath:
            self.controller.attach_file(filepath)
            filename = os.path.basename(filepath)
            self.attached_file_label.config(text=f"첨부됨: {filename}")
            print(f"GUI: 파일 첨부됨 - {filename}")
        else:
            print("GUI: 파일 선택 취소됨.")

    def _voice_input_handler(self):
        """음성 입력 버튼 클릭 시 호출될 핸들러"""
        self._disable_buttons()
        self.controller.handle_voice_input()

    def _voice_input_handler_wrapper(self, event=None):
        """단축키 이벤트를 처리하고 음성 입력 핸들러 호출"""
        print(f"단축키 핸들러 호출됨 (이벤트: {event})")
        if (
            self.controller.stt_service
            and self.stt_button
            and self.stt_button["state"] == tk.NORMAL
        ):
            self._voice_input_handler()
        else:
            print("음성 입력 단축키: STT 서비스 비활성화 또는 버튼 비활성 상태")
        return "break"

    def _start_new_chat_handler(self):
        """새 채팅 시작 버튼 클릭 시 호출될 핸들러"""
        print("GUI: 새 채팅 시작 버튼 클릭됨")
        success = self.controller.start_new_chat_session()

    def _display_response(self, text):
        """답변 영역에 텍스트 표시 (정렬 포함)"""
        self.response_area.config(state=tk.NORMAL)
        start_index = self.response_area.index(tk.END + "-1c")
        self.response_area.insert(tk.END, text + "\n\n")
        end_index = self.response_area.index(tk.END + "-1c")

        if text.startswith("User\n"):
            self.response_area.tag_add("user_message", start_index, end_index)
        elif text.startswith("AI\n"):
            self.response_area.tag_add("ai_message", start_index, end_index)

        self.response_area.see(tk.END)
        self.response_area.config(state=tk.DISABLED)

    def _check_queue(self):
        """컨트롤러의 큐를 주기적으로 확인하여 GUI 업데이트"""
        try:
            while True:
                message = self.response_queue.get_nowait()
                if isinstance(message, str):
                    if message == "System: Buttons enabled":
                        self._enable_buttons()
                    elif message == "System: Hide recording status":
                        self.update_recording_status(False)
                    elif message == "System: Clear attachment label":
                        self.clear_attachment_label()
                    elif message == "System: 새 채팅 시작됨.":
                        self.clear_chat_display()
                        self.clear_attachment_label()
                        self._display_response(
                            "System: 새로운 채팅 세션이 시작되었습니다."
                        )
                    elif message.startswith("System: Set input text|"):
                        text_to_set = message.split("|", 1)[1]
                        self.set_input_text(text_to_set)
                    elif not message.startswith("System:"):
                        self._display_response(message)
                    else:
                        print(f"GUI System Message: {message}")
                else:
                    print(
                        f"GUI Warning: Received non-string message from queue: {message}"
                    )

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
        self.attach_button.config(state=tk.DISABLED)

    def _enable_buttons(self):
        """입력 버튼 활성화"""
        self.send_button.config(state=tk.NORMAL)
        if self.stt_button:
            self.stt_button.config(state=tk.NORMAL)
        self.new_chat_button.config(state=tk.NORMAL)
        self.attach_button.config(state=tk.NORMAL)

    def _on_closing(self):
        """창 닫기 버튼 클릭 시 호출될 함수"""
        if messagebox.askokcancel("종료 확인", "애플리케이션을 종료하시겠습니까?"):
            print("GUI: 종료 요청됨. main 루프 중지 예정...")
            print("GUI: 창 소멸됨.")

    # --- 컨트롤러가 호출할 수 있는 메서드 ---
    def set_input_text(self, text: str):
        """입력 필드에 텍스트 설정"""
        self.request_entry.delete("1.0", tk.END)
        self.request_entry.insert("1.0", text)

    def update_recording_status(self, is_recording: bool):
        """녹음 상태 레이블 업데이트"""
        if self.recording_status_label:
            if is_recording:
                self.recording_status_label.config(text="🔴 녹음 중...")
                self.recording_status_label.pack(pady=(0, 5), padx=10, anchor=tk.W)
                self.recording_status_label.lift()
            else:
                self.recording_status_label.pack_forget()

    def clear_chat_display(self):
        """채팅 출력 영역 초기화"""
        self.response_area.config(state=tk.NORMAL)
        self.response_area.delete("1.0", tk.END)
        self.response_area.config(state=tk.DISABLED)

    def clear_attachment_label(self):
        """첨부 파일 레이블 초기화"""
        if self.attached_file_label:
            self.attached_file_label.config(text="")

    def run(self):
        """GUI 메인 루프 시작"""
        self.root.mainloop()
