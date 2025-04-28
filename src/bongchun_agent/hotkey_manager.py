import platform
import traceback

try:
    from pynput import keyboard
except ImportError:
    print(
        "오류: pynput 라이브러리를 찾을 수 없습니다. 시스템 전역 단축키 기능이 비활성화됩니다."
    )
    print("다음 명령어를 실행하여 설치하세요: uv add pynput")
    keyboard = None


class HotkeyManager:
    """시스템 전역 단축키 리스너를 관리하는 클래스"""

    def __init__(self, activate_callback, show_window_callback=None):
        """
        HotkeyManager를 초기화합니다.

        Args:
            activate_callback: 음성 입력 활성화 단축키 콜백.
            show_window_callback: 앱 창 표시 단축키 콜백 (선택 사항).
                                  두 콜백 모두 GUI 스레드에서 안전하게 호출되어야 합니다.
        """
        self.activate_callback = activate_callback
        self.show_window_callback = show_window_callback
        self.keyboard_available = keyboard is not None
        self.listener = None
        print(f"HotkeyManager 초기화됨. pynput 사용 가능: {self.keyboard_available}")
        print(f" - 음성 활성화 콜백: {'설정됨' if activate_callback else '없음'}")
        print(f" - 창 표시 콜백: {'설정됨' if show_window_callback else '없음'}")

    def _internal_activate_callback(self):
        """음성 입력 활성화 단축키가 눌렸을 때 내부적으로 호출되는 콜백"""
        print("음성 입력 활성화 단축키 감지됨!")
        if self.activate_callback:
            try:
                self.activate_callback()
                print("음성 입력 활성화 콜백 호출 완료.")
            except Exception as e:
                print(f"음성 입력 활성화 콜백 호출 중 오류: {e}")
                traceback.print_exc()
        else:
            print("오류: 음성 입력 활성화 콜백이 설정되지 않았습니다.")

    def _internal_show_window_callback(self):
        """앱 창 표시 단축키가 눌렸을 때 내부적으로 호출되는 콜백"""
        print("앱 창 표시 단축키 감지됨!")
        if self.show_window_callback:
            try:
                self.show_window_callback()
                print("앱 창 표시 콜백 호출 완료.")
            except Exception as e:
                print(f"앱 창 표시 콜백 호출 중 오류: {e}")
                traceback.print_exc()
        else:
            print("오류: 앱 창 표시 콜백이 설정되지 않았습니다.")

    def start_listener(self):
        """단축키 리스너를 시작합니다."""
        if not self.keyboard_available:
            print("pynput 라이브러리가 없어 전역 단축키 리스너를 시작할 수 없습니다.")
            return

        shortcut_combination = "<cmd>+<ctrl>+<shift>+t"
        if platform.system() != "Darwin":
            print(
                "경고: macOS가 아닌 환경입니다. 단축키 조합을 확인/조정해야 할 수 있습니다."
            )
            shortcut_combination = "<ctrl>+<alt>+<shift>+t"

        hotkey_map = {}
        if self.activate_callback:
            hotkey_map[shortcut_combination] = self._internal_activate_callback
            print(f" - 음성 활성화 단축키 등록: {shortcut_combination}")
        if self.show_window_callback:
            show_window_hotkey = "<f4>"
            hotkey_map[show_window_hotkey] = self._internal_show_window_callback
            print(f" - 앱 창 표시 단축키 등록: {show_window_hotkey}")

        if not hotkey_map:
            print("오류: 등록할 단축키 콜백이 없습니다.")
            return

        try:
            if self.listener and self.listener.is_alive():
                print("기존 단축키 리스너 중지 시도...")
                self.listener.stop()

            self.listener = keyboard.GlobalHotKeys(hotkey_map)
            self.listener.start()
            registered_keys = ", ".join(hotkey_map.keys())
            print(f"시스템 전역 단축키 리스너 시작됨 ({registered_keys})")
        except Exception as e:
            print(f"오류: 전역 단축키 리스너 시작 실패 - {e}")
            traceback.print_exc()
            self.listener = None

    def stop_listener(self):
        """단축키 리스너를 중지합니다."""
        if self.listener and self.listener.is_alive():
            print("단축키 리스너 종료 중...")
            try:
                self.listener.stop()
                print("단축키 리스너 종료 완료.")
            except Exception as e:
                print(f"단축키 리스너 종료 중 오류 발생: {e}")
                traceback.print_exc()
            finally:
                self.listener = None
        elif self.listener:
            print("단축키 리스너가 이미 중지되었거나 실행되지 않았습니다.")
            self.listener = None
        else:
            print("중지할 단축키 리스너가 없습니다.")


if __name__ == "__main__":
    import time

    def my_callback():
        print("--- 외부 콜백 함수 실행됨! ---")

    print("HotkeyManager 테스트 시작...")
    manager = HotkeyManager(my_callback)

    if manager.keyboard_available:
        manager.start_listener()
        print("리스너 시작됨. 단축키를 눌러 테스트하세요 (Ctrl+C로 종료).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt 감지됨. 종료 중...")
        finally:
            manager.stop_listener()
            print("HotkeyManager 테스트 종료.")
    else:
        print("pynput 사용 불가로 테스트를 진행할 수 없습니다.")
