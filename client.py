import asyncio
import os
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Optional, Dict

# mcp 라이브러리의 SSE 클라이언트와 핵심 컴포넌트를 직접 사용합니다.
from mcp import ClientSession, types as mcp_types
# stdio_client 대신 sse_client를 임포트합니다.
from mcp.client.sse import sse_client
# WebSocket 연결 예시 (필요시 주석 해제)
# from mcp.client.websocket import websocket_client

# --- 설정 ---
# 중요: 이 플레이스홀더들을 실제 값으로 교체해야 합니다.

# 1. Gemini MCP 서버 SSE 엔드포인트 URL:
#    여기에 접속하려는 MCP 서버의 SSE URL을 입력해야 합니다.
#    이 서버는 웹 서버(예: FastAPI, Starlette, Node.js 등)로 실행되어
#    지정된 URL에서 SSE 연결을 수락해야 합니다.
#    (이전 예제의 stdio 방식과는 서버 실행 방식이 다릅니다)
GEMINI_SERVER_SSE_URL = "http://localhost:8000/mcp/sse"  # <--- 예시 URL, 실제 서버 주소로 교체하세요

# 2. HTTP 헤더 (선택 사항, 인증 등에 사용):
#    서버가 인증을 요구하는 경우, 여기에 필요한 헤더를 추가합니다.
#    예: API 키를 Bearer 토큰으로 전달
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY") # <--- 환경 변수 또는 실제 키로 교체
HEADERS: Optional[Dict[str, str]] = None
if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY":
     HEADERS = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
     print("ℹ️ API 키를 Authorization 헤더에 포함하여 전송합니다.")
else:
     print("⚠️ 플레이스홀더 API 키를 사용 중입니다. 필요시 헤더 설정을 확인하세요.")


# --- 설정 확인 ---
if GEMINI_SERVER_SSE_URL == "http://localhost:8000/mcp/sse":
    print("⚠️ 경고: 예시 SSE URL을 사용 중입니다. 실제 서버 URL로 변경해야 할 수 있습니다.")


# --- 메인 클라이언트 로직 ---
async def main():
    """
    mcp 라이브러리를 직접 사용하여 SSE 방식으로
    가상의 Gemini MCP 서버에 연결하고 도구 목록을 가져옵니다.
    """
    print(f"Gemini MCP 서버(SSE)에 연결 시도 중: {GEMINI_SERVER_SSE_URL}")

    try:
        # sse_client 컨텍스트 관리자를 사용하여 서버 SSE 엔드포인트에 연결하고
        # 읽기/쓰기 스트림을 얻습니다.
        # WebSocket을 사용하려면 sse_client 대신 websocket_client(url) 사용
        async with sse_client(url=GEMINI_SERVER_SSE_URL, headers=HEADERS) as (read_stream, write_stream):
            print("✅ SSE transport 연결 성공.")

            # ClientSession 컨텍스트 관리자를 사용하여 MCP 세션을 관리합니다.
            # ClientSession 사용 방식은 stdio 방식과 동일합니다.
            async with ClientSession(read_stream, write_stream) as session:
                print("⏳ MCP 세션 초기화 중...")
                # 세션을 사용하기 전에 반드시 initialize()를 호출해야 합니다.
                await session.initialize()
                print("✅ MCP 세션 초기화 완료.")

                # Gemini 서버가 제공하는 도구 목록을 가져옵니다.
                try:
                    print("\nFetching tools from Gemini server...")
                    list_tools_result: mcp_types.ListToolsResult = await session.list_tools()
                    gemini_tools = list_tools_result.tools

                    if gemini_tools:
                        print("\n🛠️ Gemini 서버에서 사용 가능한 도구:")
                        for tool in gemini_tools:
                            print(f"  - 이름: {tool.name}")
                            print(f"    설명: {tool.description}")
                    else:
                        print("❓ 'gemini' 서버에서 도구를 찾을 수 없습니다.")
                        print("   (서버가 도구를 노출하지 않을 수 있습니다)")

                except Exception as e:
                    print(f"❌ Gemini 서버와 상호작용 중 오류 발생: {e}")

    except ImportError as e:
         # websocket_client 사용 시 의존성 누락 오류 처리
         if "websocket" in str(e).lower():
              print("❌ 오류: Websocket 연결에 필요한 'websockets' 라이브러리가 설치되지 않았습니다.")
              print("   'pip install websockets' 또는 'pip install mcp[ws]' 명령어로 설치하세요.")
         else:
              print(f"❌ 임포트 오류 발생: {e}")
    except Exception as e:
        print(f"❌ 클라이언트 실행 중 오류 발생: {e}")
        print(f"   서버가 '{GEMINI_SERVER_SSE_URL}'에서 실행 중인지, URL이 올바른지,")
        print("   네트워크 연결 및 필요한 헤더(인증 등)가 올바르게 설정되었는지 확인하세요.")

    print("\n클라이언트 작업 완료 및 연결 해제됨.")

if __name__ == "__main__":
     # SSE 방식은 서버 스크립트 경로 대신 URL로 접근하므로 경로 확인은 제거합니다.
     asyncio.run(main())