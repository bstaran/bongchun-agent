import asyncio
import os
import sys
import json
from typing import Dict, Any

import google.generativeai as genai

# .env 파일 로드
from dotenv import load_dotenv

# 새로 분리된 MCP 클라이언트 모듈 import
from client import MultiMCPClient

load_dotenv()

# --- Google AI 설정 ---
try:
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise ValueError(
            "환경 변수 'GOOGLE_API_KEY'가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    genai.configure(api_key=google_api_key)
except ValueError as e:
    print(f"오류: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Google AI 설정 중 오류 발생: {e}")
    sys.exit(1)


# --- 설정 파일 로드 및 메인 실행 로직 ---
async def run_client():
    config_path = os.path.join(os.path.dirname(__file__), "mcp_config.json")
    server_configs: Dict[str, Dict[str, Any]] = {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            full_config = json.load(f)
        loaded_servers = full_config.get("mcpServers")
        if isinstance(loaded_servers, dict):
            server_configs = loaded_servers
            print(
                f"'{config_path}'에서 {len(server_configs)}개의 서버 설정을 로드했습니다."
            )
        else:
            print(
                f"경고: '{config_path}' 파일 형식이 잘못되었거나 'mcpServers' 키가 없습니다."
            )

    except FileNotFoundError:
        print(
            f"경고: 설정 파일 '{config_path}'를 찾을 수 없습니다. 서버 설정 없이 시작합니다."
        )
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {e}")

    if not server_configs:
        print("실행할 MCP 서버 설정이 없습니다. 프로그램을 종료합니다.")
        return

    # MultiMCPClient 인스턴스 생성 (client.py 모듈 사용)
    client = MultiMCPClient()
    try:
        await client.connect_all_servers(server_configs)
        # 성공적으로 연결된 서버가 하나 이상 있을 때만 채팅 시작
        if client.sessions:
            await client.chat_loop()
        else:
            print("연결된 MCP 서버가 없어 채팅 루프를 시작할 수 없습니다.")
    except Exception as e:
        print(f"\n클라이언트 실행 중 심각한 오류 발생: {e}")
    finally:
        await client.cleanup()


if __name__ == "__main__":
    # 간단한 시스템 환경 확인 (Node.js/Java 필요 여부 등)
    # 예시: config에 npx가 있으면 node 필요, java -jar 있으면 java 필요 등
    # ... (필요시 추가) ...
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("\n프로그램 강제 종료.")
