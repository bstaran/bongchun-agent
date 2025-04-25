import tkinter as tk
from tkinter import scrolledtext


def send_prompt():
    """프롬프트 전송 버튼 클릭 시 호출되는 함수"""
    prompt_text = prompt_entry.get("1.0", tk.END).strip()
    if prompt_text:
        # TODO: 실제 LLM 호출 로직 추가
        response_text = (
            f"Received prompt: {prompt_text}\n(This is a placeholder response)"
        )
        response_area.config(state=tk.NORMAL)
        response_area.insert(tk.END, response_text + "\n")
        response_area.config(state=tk.DISABLED)
        prompt_entry.delete("1.0", tk.END)  # 입력 필드 초기화


# 메인 윈도우 생성
root = tk.Tk()
root.title("Simple GUI Chat")
root.geometry("500x400")

# 프롬프트 입력 영역
prompt_label = tk.Label(root, text="Enter your prompt:")
prompt_label.pack(pady=5)

prompt_entry = scrolledtext.ScrolledText(root, height=5, wrap=tk.WORD)
prompt_entry.pack(pady=5, padx=10, fill=tk.X)
prompt_entry.focus()  # 시작 시 포커스 설정

# 전송 버튼
send_button = tk.Button(root, text="Send", command=send_prompt)
send_button.pack(pady=5)

# 답변 출력 영역
response_label = tk.Label(root, text="Response:")
response_label.pack(pady=5)

response_area = scrolledtext.ScrolledText(
    root, height=15, wrap=tk.WORD, state=tk.DISABLED
)
response_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

# 메인 루프 시작
root.mainloop()
