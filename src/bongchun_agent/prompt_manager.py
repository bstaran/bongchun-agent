import os
from tkinter import messagebox
from .app_config import NO_PROMPT_OPTION


class PromptManager:
    """프롬프트 로딩 및 관리를 담당하는 클래스"""

    def __init__(self, prompt_dir="prompt"):
        """
        PromptManager를 초기화합니다.

        Args:
            prompt_dir (str): 프롬프트 파일이 있는 디렉토리 경로.
        """
        self.prompt_dir = prompt_dir
        if not os.path.isdir(self.prompt_dir):
            print(
                f"경고: 프롬프트 디렉토리 '{self.prompt_dir}'를 찾을 수 없습니다. 생성합니다."
            )
            try:
                os.makedirs(self.prompt_dir)
            except OSError as e:
                messagebox.showerror("오류", f"프롬프트 디렉토리 생성 실패: {e}")
                self.default_prompt_path = None
                self.default_system_prompt = None
                self.available_prompts = [NO_PROMPT_OPTION]
                return

        self.default_prompt_path = os.path.join(self.prompt_dir, "default.txt")
        self.default_system_prompt = self._load_default_system_prompt()
        self.available_prompts = self._load_prompts()
        print(
            f"PromptManager 초기화 완료. 사용 가능한 프롬프트: {self.available_prompts}"
        )
        if self.default_system_prompt:
            print("기본 시스템 프롬프트 로드됨.")
        else:
            print("기본 시스템 프롬프트 없음.")

    def _load_default_system_prompt(self):
        """기본 시스템 프롬프트 파일(default.txt)의 내용을 로드합니다."""
        if self.default_prompt_path and os.path.exists(self.default_prompt_path):
            try:
                with open(self.default_prompt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    print(f"기본 시스템 프롬프트 로드됨: {self.default_prompt_path}")
                    return content
            except OSError as e:
                messagebox.showerror(
                    "오류", f"기본 프롬프트 파일을 읽을 수 없습니다: {e}"
                )
            except Exception as e:
                messagebox.showerror(
                    "오류", f"기본 프롬프트 읽기 중 예상치 못한 오류 발생: {e}"
                )
        else:
            print(
                f"경고: 기본 시스템 프롬프트 '{self.default_prompt_path}'를 찾을 수 없습니다. 기본 시스템 프롬프트가 사용되지 않습니다."
            )
        return None

    def _load_prompts(self):
        """프롬프트 디렉토리에서 .txt 파일 이름(확장자 제외)을 로드하고 '없음' 옵션을 추가합니다."""
        prompts = [NO_PROMPT_OPTION]
        if os.path.isdir(self.prompt_dir):
            try:
                for filename in os.listdir(self.prompt_dir):
                    if filename.endswith(".txt") and filename != "default.txt":
                        prompts.append(os.path.splitext(filename)[0])
            except OSError as e:
                messagebox.showerror(
                    "오류", f"프롬프트 디렉토리를 읽을 수 없습니다: {e}"
                )

        if len(prompts) == 1:
            print("경고: 'prompt' 디렉토리에서 추가 프롬프트를 찾을 수 없습니다.")
        return prompts

    def load_selected_prompt(self, prompt_name):
        """선택된 *추가* 프롬프트 파일의 내용을 로드하여 반환합니다."""
        if prompt_name == NO_PROMPT_OPTION or not prompt_name:
            print("추가 프롬프트가 선택되지 않았습니다.")
            return ""

        prompt_file_path = os.path.join(self.prompt_dir, f"{prompt_name}.txt")

        try:
            if os.path.exists(prompt_file_path):
                with open(prompt_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"추가 프롬프트 내용 로드됨: {prompt_file_path}")
                return content
            else:
                messagebox.showerror(
                    "오류",
                    f"선택한 프롬프트 파일 '{prompt_file_path}'을(를) 예기치 않게 찾을 수 없습니다.",
                )
                return ""
        except OSError as e:
            messagebox.showerror("오류", f"프롬프트 파일을 읽을 수 없습니다: {e}")
            return ""
        except Exception as e:
            messagebox.showerror("오류", f"프롬프트 읽기 중 예상치 못한 오류 발생: {e}")
            return ""
