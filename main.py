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
    from PyQt6.QtWidgets import QApplication
    from bongchun_agent.gui import BongchunAgentGUI  # 클래스 이름 변경
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

    # 0. QApplication 인스턴스 생성
    app = QApplication(sys.argv)
    print("QApplication 인스턴스 생성됨.")

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
    # BongchunAgentGUI 생성자에 필요한 인자 전달
    gui = BongchunAgentGUI(
        client=app_controller.mcp_client,
        prompt_manager=prompt_manager,
        hotkey_manager=app_controller.hotkey_manager,
        app_controller=app_controller,
    )

    # 4. 컨트롤러에 GUI 참조 설정
    app_controller.set_gui(gui)

    # 5. GUI 실행 및 종료 처리
    try:
        print("GUI 실행 시작...")
        gui.show()
        print("PyQt6 이벤트 루프 시작...")
        exit_code = app.exec()
        print(f"PyQt6 이벤트 루프 종료됨 (종료 코드: {exit_code}).")
        sys.exit(exit_code)

    except Exception as e:
        print(f"GUI 실행 중 오류 발생:", file=sys.stderr)
        traceback.print_exc()

    finally:
        print("애플리케이션 종료 처리 시작...")

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

        if async_loop.is_running():
            print("비동기 이벤트 루프 종료 요청...")
            async_loop.call_soon_threadsafe(async_loop.stop)
            print("비동기 이벤트 루프 종료 요청 완료.")
        else:
            print("비동기 이벤트 루프가 이미 종료되었습니다.")

        print("애플리케이션 종료 처리 완료.")


if __name__ == "__main__":
    main()
