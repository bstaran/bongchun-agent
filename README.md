# Bongchun Agent

Bongchun Agent는 시스템 전역 단축키를 통해 Google Gemini AI 모델과 상호작용하고, 음성 인식을 지원하며, MCP(Model Context Protocol) 서버를 통해 확장 가능한 기능을 제공하는 데스크톱 애플리케이션입니다.

## 주요 기능

- **AI 모델 연동:** Google Gemini AI 모델을 활용하여 다양한 작업을 수행합니다.
- **시스템 전역 단축키:**
  - 음성 입력 활성화 (기본값: macOS `<cmd>+<ctrl>+<shift>+t`, Windows/Linux `<ctrl>+<alt>+<shift>+t`)
  - 애플리케이션 창 표시/숨김 (기본값: `<f4>`)
- **GUI 인터페이스:** PyQt6 기반의 사용자 인터페이스를 제공합니다.
- **음성-텍스트 변환 (STT):** 음성 입력을 통해 요청합니다.
- **MCP 서버:**
  - `terminal_executor_server`: 터미널 명령어를 실행하는 MCP 서버를 포함합니다.
  - 다른 MCP 서버를 추가하여 기능을 확장할 수 있습니다.
- **설정 관리:** API 키 및 기타 설정을 관리합니다.
- **프롬프트 관리:** 다양한 작업에 사용될 프롬프트를 관리합니다.

## 기술 스택

- **언어:** Python 3.x
- **GUI:** PyQt6
- **단축키:** pynput
- **AI:** Google Generative AI SDK
- **패키지 관리:** uv
- **프로토콜:** Model Context Protocol (MCP)

## 설치 및 설정

1.  **저장소 복제:**

    ```bash
    git clone <repository_url>
    cd bongchun-agent
    ```

2.  **Python 버전 확인:**

    - 프로젝트 루트의 `.python-version` 파일에 명시된 Python 버전을 사용하세요.

3.  **uv 설치:**

    - `uv`가 설치되어 있지 않다면 설치합니다. [uv 설치 가이드](https://github.com/astral-sh/uv#installation)를 참고하세요.

4.  **의존성 설치:**

    ```bash
    uv sync
    ```

5.  **환경 변수 설정:**

    - `example.env` 파일을 복사하여 `.env` 파일을 생성합니다.
    - `.env` 파일 내에 필요한 API 키 (예: `GOOGLE_API_KEY`) 및 기타 설정을 입력합니다.

6.  **MCP 설정:**

    - `example.mcp_config.json` 파일을 복사하여 `mcp_config.json` 파일을 생성합니다.
    - 필요에 따라 `mcp_config.json` 파일의 서버 설정을 수정합니다.

## 실행 방법

1.  **메인 애플리케이션 실행:**

    ```bash
    uv run main.py
    ```

2.  **(선택) MCP 서버 실행:**

    - `mcp_config.json`에 정의된 로컬 서버가 있다면, 별도의 터미널에서 해당 서버를 실행해야 할 수 있습니다.

    ```bash
    # 예시: 터미널 실행 서버 (실제 명령어는 다를 수 있음)
    python src/mcp_server/terminal_executor_server.py
    ```

## 단축키

- **음성 입력 활성화:**
  - macOS: `Command + Control + Shift + T`
  - Windows/Linux: `Ctrl + Alt + Shift + T`
- **앱 창 표시/숨김:** `F4`

- macOS의 경우 실행하는 터미널 앱이 Input Mornitoring에 추가되어 있어야 합니다.
  _참고: 단축키는 `src/bongchun_agent/hotkey_manager.py` 파일에서 수정할 수 있습니다._

## 라이선스

[LICENSE](./LICENSE)
