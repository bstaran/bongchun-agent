import platform
import traceback
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from pynput import keyboard
except ImportError:
    print(
        "오류: pynput 라이브러리를 찾을 수 없습니다. 시스템 전역 단축키 기능이 비활성화됩니다."
    )
    print("다음 명령어를 실행하여 설치하세요: uv add pynput")
    keyboard = None


class HotkeyManager(QObject):
    """시스템 전역 단축키 리스너를 관리하고 PyQt 시그널을 발생시키는 클래스"""

    activate_signal = pyqtSignal()
    show_window_signal = pyqtSignal()

    def __init__(self, parent=None):
        """
        HotkeyManager를 초기화합니다.
        """
        super().__init__(parent)
        self.keyboard_available = keyboard is not None
        self.listener = None
        self.hotkey_map = {}
        print(f"HotkeyManager 초기화됨. pynput 사용 가능: {self.keyboard_available}")

    def _internal_activate_callback(self):
        """음성 입력 활성화 단축키가 눌렸을 때 시그널 발생"""
        print("[HotkeyManager DEBUG] _internal_activate_callback 호출됨")
        print("음성 입력 활성화 단축키 감지됨!")
        self.activate_signal.emit()
        print("[HotkeyManager DEBUG] activate_signal emit 완료")

    def _internal_show_window_callback(self):
        """앱 창 표시 단축키가 눌렸을 때 시그널 발생"""
        print("[HotkeyManager DEBUG] _internal_show_window_callback 호출됨")
        print("앱 창 표시 단축키 감지됨!")
        self.show_window_signal.emit()
        print("[HotkeyManager DEBUG] show_window_signal emit 완료")

    def register_hotkeys(self, activate=True, show_window=True, paste=True):
        """
        등록할 단축키를 설정합니다. 리스너 시작 전에 호출해야 합니다.

        Args:
            activate (bool): 음성 활성화 단축키 등록 여부 (기본값: True)
            show_window (bool): 창 표시 단축키 등록 여부 (기본값: True)
            paste (bool): 붙여넣기 단축키 등록 여부 (기본값: True)
        """
        self.hotkey_map = {}

        shortcut_combination = "<cmd>+<ctrl>+<shift>+t"
        if platform.system() != "Darwin":
            print(
                "경고: macOS가 아닌 환경입니다. 단축키 조합을 확인/조정해야 할 수 있습니다."
            )
            shortcut_combination = "<ctrl>+<alt>+<shift>+t"
        else:
            pass

        if activate:
            self.hotkey_map[shortcut_combination] = self._internal_activate_callback
            print(f" - 음성 활성화 단축키 등록 예정: {shortcut_combination}")
        if show_window:
            show_window_hotkey = "<f4>"
            self.hotkey_map[show_window_hotkey] = self._internal_show_window_callback
            print(f" - 앱 창 표시/숨김 단축키 등록 예정: {show_window_hotkey}")

    def start_listener(self):
        """단축키 리스너를 시작합니다."""
        if not self.keyboard_available:
            print("pynput 라이브러리가 없어 전역 단축키 리스너를 시작할 수 없습니다.")
            return

        if not self.hotkey_map:
            print(
                "오류: 등록된 단축키가 없습니다. register_hotkeys()를 먼저 호출하세요."
            )
            return

        try:
            if self.listener and self.listener.is_alive():
                print("기존 단축키 리스너 중지 시도...")
                self.listener.stop()

            self.listener = keyboard.GlobalHotKeys(self.hotkey_map)
            self.listener.start()
            registered_keys = ", ".join(self.hotkey_map.keys())
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
                import threading

                stop_event = threading.Event()

                def stop_thread():
                    try:
                        self.listener.stop()
                    except Exception as inner_e:
                        print(f"리스너 종료 중 내부 오류 (무시됨): {inner_e}")
                    finally:
                        stop_event.set()

                thread = threading.Thread(target=stop_thread, daemon=True)
                thread.start()
                if not stop_event.wait(timeout=2.0):
                    print("경고: 리스너 종료 확인 시간 초과.")
                else:
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
