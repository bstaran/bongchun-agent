import asyncio
import threading
import sys
import os
import traceback

# 프로젝트 루트 경로 설정 및 src 경로 추가
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
    print(f"Added '{src_path}' to sys.path")

try:
    from bongchun_agent.app_config import load_config
    from bongchun_agent.utils import run_async_loop
    from bongchun_agent.gui import ChatGUI
    from bongchun_agent.app_controller import AppController
    from bongchun_agent.prompt_manager import PromptManager
    from bongchun_agent.hotkey_manager import HotkeyManager

    print("Successfully imported necessary components.")
except ImportError as e:
    print(f"오류: 필요한 모듈을 임포트할 수 없습니다.", file=sys.stderr)
    print(f"PYTHONPATH: {sys.path}", file=sys.stderr)
    print(f"오류 상세 정보: {e}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"모듈 임포트 중 예상치 못한 오류 발생:", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)


def main():
    """
    bongchun_agent 애플리케이션의 메인 진입점.
    설정 로드, 컴포넌트 초기화, GUI 실행 및 종료 처리를 담당합니다.
    """
    print("main.py 실행됨. bongchun_agent 애플리케이션 시작...")

    # 1. 설정 로드
    config_data = None
    try:
        config_data = load_config()
        if config_data is None:
            print("설정 로드 실패. 애플리케이션을 종료합니다.", file=sys.stderr)
            sys.exit(1)
        print("설정 로드 완료.")
    except Exception as e:
        print(f"설정 로드 중 오류 발생: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    # 2. 비동기 이벤트 루프 설정 및 시작
    async_loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(
        target=run_async_loop, args=(async_loop,), daemon=True
    )
    loop_thread.start()
    print("비동기 이벤트 루프 시작됨.")

    # 3. 주요 컴포넌트 인스턴스화
    prompt_manager = PromptManager()
    app_controller = AppController(
        loop=async_loop, config=config_data, prompt_manager=prompt_manager
    )
    gui = ChatGUI(controller=app_controller)

    # 4. 컨트롤러에 GUI 참조 설정
    app_controller.set_gui(gui)

    # 5. 단축키 관리자 초기화 및 시작
    hotkey_manager = None
    try:
        hotkey_manager = HotkeyManager(callback=gui._voice_input_handler_wrapper)
        hotkey_manager.start_listener()
        print("단축키 리스너 시작됨.")
    except ImportError:
        print(
            "경고: pynput 라이브러리를 찾을 수 없어 단축키 기능이 비활성화됩니다.",
            file=sys.stderr,
        )
    except AttributeError:
        print(
            "경고: ChatGUI에 '_voice_input_handler_wrapper' 메서드가 없습니다. 단축키 기능이 비활성화됩니다.",
            file=sys.stderr,
        )
        hotkey_manager = None
    except Exception as e:
        print(f"단축키 리스너 시작 중 오류 발생: {e}", file=sys.stderr)
        hotkey_manager = None

    # 6. GUI 실행 및 종료 처리
    try:
        print("GUI 실행 시작...")
        gui.run()
        print("GUI 애플리케이션이 정상적으로 종료되었습니다.")

    except Exception as e:
        print(f"GUI 실행 중 오류 발생:", file=sys.stderr)
        traceback.print_exc()

    finally:
        print("애플리케이션 종료 처리 시작...")
        if hotkey_manager:
            try:
                hotkey_manager.stop_listener()
                print("단축키 리스너 중지됨.")
            except Exception as e:
                print(f"단축키 리스너 중지 중 오류: {e}", file=sys.stderr)

        if app_controller:
            try:
                if async_loop.is_running():
                    print("AppController 리소스 정리 요청...")
                    future = asyncio.run_coroutine_threadsafe(
                        app_controller.cleanup(), async_loop
                    )
                    future.result(timeout=10)
                    print("AppController 리소스 정리 완료.")
                else:
                    print(
                        "경고: 비동기 루프가 실행 중이지 않아 AppController 정리를 건너뜁니다.",
                        file=sys.stderr,
                    )
            except TimeoutError:
                print("AppController 정리 중 타임아웃 발생.", file=sys.stderr)
            except Exception as e:
                print(f"AppController 정리 중 오류 발생: {e}", file=sys.stderr)
                traceback.print_exc()

        # 비동기 루프 중지
        if async_loop.is_running():
            print("비동기 이벤트 루프 종료 요청...")
            async_loop.call_soon_threadsafe(async_loop.stop)
            print("비동기 이벤트 루프 종료 요청 완료.")
        else:
            print("비동기 이벤트 루프가 이미 종료되었습니다.")

        print("애플리케이션 종료 처리 완료.")


if __name__ == "__main__":
    main()
