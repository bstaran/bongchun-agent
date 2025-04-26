import sys
import os
import traceback

project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)
    print(f"Added '{src_path}' to sys.path")

try:
    from src.bongchun_agent.app import run_gui

    print("Successfully imported run_gui from bongchun_agent.app")
except ImportError as e:
    print(
        f"오류: 필요한 모듈 'bongchun_agent.app'을 임포트할 수 없습니다.",
        file=sys.stderr,
    )
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
    bongchun_agent GUI 애플리케이션을 실행합니다.
    """
    print("main.py 실행됨. bongchun_agent GUI 시작...")
    try:
        run_gui()  # 임포트한 함수 호출
        print("GUI 애플리케이션이 정상적으로 종료되었습니다.")
    except Exception as e:
        print(f"GUI 실행 중 오류 발생:", file=sys.stderr)
        traceback.print_exc()


if __name__ == "__main__":
    main()
