import asyncio
import os
import sys
import json
import traceback
from typing import Optional, List, Dict, Any, Tuple
from contextlib import AsyncExitStack

# MCP 관련 import
from mcp import ClientSession, StdioServerParameters, types as mcp_types
from mcp.client.stdio import stdio_client

# 다른 전송 방식 클라이언트 임포트 (필요시)
from mcp.client.sse import sse_client

# from mcp.client.websocket import websocket_client

# Google Gemini 관련 import (MultiMCPClient 클래스에서 사용)
import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration


# --- MCP 클라이언트 클래스 ---
class MultiMCPClient:
    def __init__(self):
        # 여러 세션을 관리하기 위한 딕셔너리
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.all_mcp_tools: List[mcp_types.Tool] = []  # 모든 서버의 도구 통합
        self.tool_to_server_map: Dict[str, str] = {}  # 도구 이름 -> 서버 이름 매핑

        # Google Gemini 모델 초기화 (기존과 유사)
        # 참고: API 키 설정은 main.py에서 처리되므로 여기서는 모델만 초기화
        self.gemini_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-preview-04-17",
            # safety_settings=...
            # generation_config=...
        )
        self.chat_session = self.gemini_model.start_chat(
            enable_automatic_function_calling=True
        )

    # MultiMCPClient 클래스 내부에 추가될 헬퍼 함수
    def _clean_schema_for_gemini(
        self, schema: Optional[Dict[str, Any]], tool_name: str, path: str = "root"
    ) -> Optional[Dict[str, Any]]:
        """Gemini FunctionDeclaration 스키마에 맞게 불필요한 필드를 제거하는 재귀 함수"""
        if not isinstance(schema, dict):
            # inputSchema 자체가 없거나 dict가 아니면 None 반환 (parameters 없이 생성 시도)
            if path == "root":
                print(
                    f"경고 [{tool_name}]: inputSchema가 없거나 딕셔너리가 아닙니다. parameters 없이 도구를 정의합니다."
                )
            else:
                print(
                    f"경고 [{tool_name}]: 스키마 경로 '{path}'의 값이 딕셔너리가 아닙니다: {schema}. 이 부분을 제외합니다."
                )
            return None

        cleaned_schema = {}
        ALLOWED_FIELDS = {
            "type",
            "description",
            "properties",
            "required",
            "enum",
            "items",
        }
        VALID_JSON_SCHEMA_TYPES = {
            "string",
            "number",
            "integer",
            "boolean",
            "array",
            "object",
        }

        # 1. type 검증 및 설정 (필수)
        schema_type = schema.get("type")
        if isinstance(schema_type, str) and schema_type in VALID_JSON_SCHEMA_TYPES:
            cleaned_schema["type"] = schema_type
        else:
            # 타입이 없거나 유효하지 않으면 기본값 'object' 또는 'string' 추론
            default_type = "object" if "properties" in schema else "string"
            print(
                f"경고 [{tool_name}]: 스키마 경로 '{path}'의 type ('{schema_type}')이 유효하지 않습니다. 기본값 '{default_type}'를 사용합니다."
            )
            cleaned_schema["type"] = default_type

        # 2. description 설정 (선택)
        description = schema.get("description")
        if description is not None:
            cleaned_schema["description"] = (
                str(description) if not isinstance(description, str) else description
            )

        # 3. enum 설정 (선택, type이 string/number/integer일 때 유효)
        enum_values = schema.get("enum")
        current_type = cleaned_schema.get("type")
        if isinstance(enum_values, list) and current_type in [
            "string",
            "number",
            "integer",
        ]:
            # 모든 요소가 해당 타입인지 확인 (여기서는 간단히 문자열/숫자만 허용)
            valid_enum = [
                val for val in enum_values if isinstance(val, (str, int, float, bool))
            ]  # bool 추가
            if valid_enum:
                cleaned_schema["enum"] = valid_enum
            else:
                print(
                    f"경고 [{tool_name}]: 스키마 경로 '{path}'의 enum 값들이 유효하지 않습니다: {enum_values}"
                )

        # 4. properties 처리 (type이 'object'일 때)
        if current_type == "object":
            properties = schema.get("properties")
            if isinstance(properties, dict):
                cleaned_properties = {}
                for prop_name, prop_schema in properties.items():
                    # 재귀 호출로 하위 속성 스키마 정리
                    cleaned_prop = self._clean_schema_for_gemini(
                        prop_schema, tool_name, f"{path}.properties.{prop_name}"
                    )
                    if cleaned_prop:  # 유효한 스키마만 추가
                        cleaned_properties[prop_name] = cleaned_prop
                if cleaned_properties:  # 빈 properties는 추가하지 않음
                    cleaned_schema["properties"] = cleaned_properties

            # 5. required 처리 (type이 'object'이고 properties가 있을 때)
            if "properties" in cleaned_schema:  # 정리된 properties가 있어야 함
                required = schema.get("required")
                if isinstance(required, list):
                    # required 항목이 문자열이고 cleaned_properties에 존재하는지 확인
                    valid_required = [
                        req
                        for req in required
                        if isinstance(req, str) and req in cleaned_schema["properties"]
                    ]
                    if valid_required:  # 빈 required는 추가하지 않음
                        cleaned_schema["required"] = valid_required

        # 6. items 처리 (type이 'array'일 때)
        elif current_type == "array":
            items_schema = schema.get("items")
            # 재귀 호출로 배열 항목 스키마 정리
            cleaned_items = self._clean_schema_for_gemini(
                items_schema, tool_name, f"{path}.items"
            )
            if cleaned_items:  # 유효한 스키마만 추가
                cleaned_schema["items"] = cleaned_items
            else:
                print(
                    f"경고 [{tool_name}]: 스키마 경로 '{path}' (배열 타입)에 유효한 'items' 정의가 없습니다."
                )

        # 최종적으로 유효한 키가 하나라도 있는지 확인 (최소 type은 있어야 함)
        return cleaned_schema if cleaned_schema else None  # 완전히 비면 None 반환

    def _mcp_tools_to_gemini_tools(self) -> List[Tool]:
        """
        통합된 MCP 도구 목록을 Gemini Tool 객체 리스트로 변환합니다.
        MCP Tool의 name, description을 사용하고,
        inputSchema를 Gemini FunctionDeclaration의 parameters로 변환합니다.
        이때 Gemini 스키마에서 지원하지 않는 필드는 제거합니다.
        """
        gemini_function_declarations: List[FunctionDeclaration] = []
        processed_tool_names = set()

        for tool in self.all_mcp_tools:
            if tool.name in processed_tool_names:
                print(
                    f"경고: 중복된 도구 이름 '{tool.name}' 발견. 첫 번째 도구만 사용합니다."
                )
                continue
            processed_tool_names.add(tool.name)

            try:
                # MCP inputSchema를 Gemini 호환 스키마로 정리
                cleaned_parameters = self._clean_schema_for_gemini(
                    tool.inputSchema, tool.name
                )

                # FunctionDeclaration 생성 시도
                func_decl = FunctionDeclaration(
                    name=tool.name,
                    description=(
                        str(tool.description)
                        if not isinstance(tool.description, str)
                        else tool.description
                    ),
                    # cleaned_parameters가 None이거나 비어있으면 parameters 자체를 전달하지 않음
                    parameters=cleaned_parameters if cleaned_parameters else None,
                )
                gemini_function_declarations.append(func_decl)
            except Exception as e:
                # FunctionDeclaration 생성 시 여전히 오류가 발생할 수 있음
                print(f"오류: 도구 '{tool.name}'의 FunctionDeclaration 생성 실패 - {e}")
                # 실패 시 사용된 파라미터 로깅 (cleaned_parameters가 정의되었는지 확인)
                params_for_log = (
                    cleaned_parameters
                    if "cleaned_parameters" in locals()
                    else tool.inputSchema
                )
                print(
                    f"도구 이름: '{tool.name}'\n도구 설명: '{tool.description}'\n사용된 parameters: {json.dumps(params_for_log, indent=2)}"
                )

        return (
            [Tool(function_declarations=gemini_function_declarations)]
            if gemini_function_declarations
            else []
        )

    async def _connect_and_init_stdio(self, server_name: str, config: Dict[str, Any]):
        """지정된 stdio 서버에 연결하고 초기화하는 내부 함수"""
        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env", os.environ.copy())  # 없으면 현재 환경 사용
        if not command:
            print(
                f"경고: 서버 '{server_name}' 설정에 'command'가 없어 건너<0xEB><0x9C><0x9C>니다."
            )
            return

        server_params = StdioServerParameters(command=command, args=args, env=env)
        try:
            print(f"'{server_name}' (stdio) 연결 시도: {command} {' '.join(args)}")
            # enter_async_context를 사용하여 exit_stack으로 관리
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            await session.initialize()
            print(f"✅ '{server_name}' 세션 초기화 완료.")
            self.sessions[server_name] = session

            # 이 서버의 도구 가져오기
            list_tools_result = await session.list_tools()
            server_tools = list_tools_result.tools if list_tools_result else []
            print(f"  '{server_name}' 제공 도구: {[t.name for t in server_tools]}")
            self.all_mcp_tools.extend(server_tools)
            for tool in server_tools:
                if tool.name in self.tool_to_server_map:
                    print(
                        f"경고: 도구 이름 '{tool.name}'이(가) '{self.tool_to_server_map[tool.name]}' 서버와 '{server_name}' 서버에 중복됩니다. '{server_name}'의 도구를 사용합니다."
                    )
                self.tool_to_server_map[tool.name] = server_name  # 도구 <-> 서버 매핑

        except Exception as e:
            print(f"❌ '{server_name}' 서버 연결 또는 초기화 실패: {e}")
            # 연결 실패 시 해당 세션은 self.sessions에 추가되지 않음

    # --- SSE/WebSocket 연결 함수 (필요시 추가) ---
    async def _connect_and_init_sse(self, server_name: str, config: Dict[str, Any]):
        """지정된 SSE 서버에 연결하고 초기화하는 내부 함수"""
        url = config.get("url")
        headers = config.get("headers")  # 인증 등
        if not url:
            print(
                f"경고: SSE 서버 '{server_name}' 설정에 'url'이 없어 건너<0xEB><0x9C><0x9C>니다."
            )
            return
        try:
            print(f"'{server_name}' (SSE) 연결 시도: {url}")
            sse_transport = await self.exit_stack.enter_async_context(
                sse_client(url=url, headers=headers)
            )
            read_stream, write_stream = sse_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            print(f"✅ '{server_name}' (SSE) 세션 초기화 완료.")
            self.sessions[server_name] = session
            # 도구 가져오기 및 매핑 (stdio와 동일 로직)
            list_tools_result = await session.list_tools()
            server_tools = list_tools_result.tools if list_tools_result else []
            print(f"  '{server_name}' 제공 도구: {[t.name for t in server_tools]}")
            self.all_mcp_tools.extend(server_tools)
            for tool in server_tools:
                if tool.name in self.tool_to_server_map:
                    print(
                        f"경고: 도구 이름 '{tool.name}' 중복. '{server_name}'의 도구를 사용합니다."
                    )
                self.tool_to_server_map[tool.name] = server_name
        except Exception as e:
            print(f"❌ '{server_name}' (SSE) 서버 연결 또는 초기화 실패: {e}")

    async def connect_all_servers(self, server_configs: Dict[str, Dict[str, Any]]):
        """설정 파일에 정의된 모든 서버에 병렬로 연결합니다."""
        tasks = []
        for server_name, config in server_configs.items():
            transport_type = config.get("transport", "stdio").lower()  # 기본값 stdio

            if transport_type == "stdio":
                # command 필드가 있는지 확인 (stdio 필수)
                if "command" in config:
                    tasks.append(self._connect_and_init_stdio(server_name, config))
                else:
                    print(
                        f"경고: stdio 서버 '{server_name}' 설정에 'command'가 없어 건너<0xEB><0x9C><0x9C>니다."
                    )
            elif transport_type == "sse":
                # url 필드가 있는지 확인 (sse 필수)
                if "url" in config:
                    tasks.append(self._connect_and_init_sse(server_name, config))
                else:
                    print(
                        f"경고: SSE 서버 '{server_name}' 설정에 'url'이 없어 건너<0xEB><0x9C><0x9C>니다."
                    )
            # TODO: WebSocket 등 다른 전송 방식 지원 추가
            else:
                print(
                    f"경고: 지원되지 않는 전송 방식 '{transport_type}' (서버: {server_name}). 건너<0xEB><0x9C><0x9C>니다."
                )

        await asyncio.gather(*tasks)  # 모든 연결 시도를 병렬로 실행
        print(
            f"\n총 {len(self.sessions)}개의 서버에 성공적으로 연결 및 초기화되었습니다."
        )
        print(
            f"사용 가능한 전체 MCP 도구: {[tool.name for tool in self.all_mcp_tools]}"
        )

    async def process_query(self, query: str) -> str:
        """사용자 쿼리를 처리하고, 필요시 올바른 MCP 서버의 도구를 호출합니다."""
        if not self.sessions:
            return "오류: 연결된 MCP 서버가 없습니다."

        print("\nGemini 모델에게 요청 전송 중...")
        gemini_tools = self._mcp_tools_to_gemini_tools()
        print(
            f"[DEBUG] Gemini에게 전달될 도구 정보: {len(gemini_tools[0].function_declarations) if gemini_tools else 0}개"
        )

        try:
            response = await self.chat_session.send_message_async(
                query, tools=gemini_tools
            )

            final_text_parts = []
            while True:
                if not response.candidates:
                    print("경고: Gemini로부터 응답 후보를 받지 못했습니다.")
                    break

                # 수정: parts 접근 전에 content 존재 여부 확인
                candidate_content = response.candidates[0].content
                if not candidate_content or not candidate_content.parts:
                    print("경고: Gemini 응답에 내용(content or parts)이 없습니다.")
                    if final_text_parts:
                        break
                    else:
                        return "오류: AI로부터 유효한 응답을 받지 못했습니다."

                latest_response_part = candidate_content.parts[0]

                if latest_response_part.text:
                    final_text_parts.append(latest_response_part.text)
                    break

                elif (
                    hasattr(latest_response_part, "function_call")
                    and latest_response_part.function_call
                ):
                    function_call = latest_response_part.function_call
                    tool_name = function_call.name

                    # Gemini가 호출하려는 도구가 어떤 서버에 속하는지 확인
                    target_server_name = self.tool_to_server_map.get(tool_name)
                    if not target_server_name:
                        print(
                            f"❌ 오류: Gemini가 알 수 없는 도구 '{tool_name}' 호출을 시도했습니다."
                        )
                        final_text_parts.append(
                            f"[오류: 알 수 없는 도구 '{tool_name}']"
                        )
                        break  # 오류 발생 시 중단

                    target_session = self.sessions.get(target_server_name)
                    if not target_session:
                        print(
                            f"❌ 오류: 도구 '{tool_name}'을 처리할 서버 '{target_server_name}'의 세션을 찾을 수 없습니다."
                        )
                        final_text_parts.append(f"[오류: 도구 '{tool_name}' 처리 실패]")
                        break  # 오류 발생 시 중단

                    # 인자 파싱 (기존 코드 유지)
                    tool_args_dict = {}
                    if hasattr(function_call, "args") and function_call.args:
                        try:
                            tool_args_dict = {
                                key: value for key, value in function_call.args.items()
                            }
                        except Exception as e:
                            print(
                                f"경고: Gemini 함수 호출 인자 파싱 중 오류: {e}. 빈 인자로 시도합니다."
                            )
                            tool_args_dict = {}

                    print(
                        f"[Gemini 요청: 서버 '{target_server_name}'의 MCP 도구 '{tool_name}' 호출 (인자: {tool_args_dict})]"
                    )
                    final_text_parts.append(
                        f"[도구 호출: {tool_name}({json.dumps(tool_args_dict, ensure_ascii=False)})]"
                    )

                    # 해당 서버의 세션을 사용하여 MCP 도구 호출
                    try:
                        # ★★★★★ 핵심: 올바른 세션으로 도구 호출 ★★★★★
                        mcp_result = await target_session.call_tool(
                            tool_name, arguments=tool_args_dict
                        )
                        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

                        # 결과 처리 (기존 코드 유지, 오류 발생 시 tool_result에 반영되도록 수정 필요)
                        result_content = "[Tool executed successfully]"  # 기본 메시지
                        if mcp_result.isError:
                            result_content = f"[오류: 도구 '{tool_name}' 실행 실패]"
                            print(f"MCP 도구 '{tool_name}' 실행 오류 보고됨.")
                        elif mcp_result.content:
                            # 간단히 첫 번째 텍스트 콘텐츠 사용 (실제로는 더 복잡한 처리 필요)
                            if isinstance(mcp_result.content[0], mcp_types.TextContent):
                                result_content = mcp_result.content[0].text
                                print(
                                    f"[MCP 도구 '{tool_name}' 결과]: {result_content[:200]}..."
                                )  # 너무 길면 자르기
                            else:
                                result_content = f"[MCP 도구 '{tool_name}' 결과 type: {type(mcp_result.content[0])}]"
                                print(result_content)

                        # Gemini에게 함수 실행 결과를 전달
                        response = await self.chat_session.send_message_async(
                            [
                                {
                                    "function_response": {
                                        "name": tool_name,
                                        "response": {"content": result_content},
                                    }
                                }
                            ],
                            tools=gemini_tools,
                        )
                        # final_text_parts.append(result_content) # 응답 결과는 Gemini가 생성하도록 함

                    except Exception as tool_error:
                        print(f"MCP 도구 '{tool_name}' 실행 중 오류: {tool_error}")
                        final_text_parts.append(
                            f"[오류: 도구 '{tool_name}' 실행 실패 - {tool_error}]"
                        )
                        break  # 오류 발생 시 중단
                else:
                    print(
                        f"경고: Gemini로부터 예상치 못한 응답 형식을 받았습니다: {latest_response_part}"
                    )
                    break  # 루프 종료

            return "\n".join(final_text_parts)

        except Exception as e:
            print(f"Gemini API 호출 중 오류 발생: {e}")
            return f"오류: AI 모델과 통신 중 문제가 발생했습니다 - {e}"

    async def chat_loop(self):
        """대화형 채팅 루프를 실행합니다."""
        print("\n--- MCP 클라이언트 (Gemini 연동, 다중 서버) 시작 ---")
        print("쿼리를 입력하거나 'quit'를 입력하여 종료하세요.")

        while True:
            try:
                query = await asyncio.to_thread(input, "\n나의 요청: ")
                query = query.strip()
                if query.lower() == "quit":
                    break
                if not query:
                    continue
                response_text = await self.process_query(query)
                print("\nAI 응답:")
                print(response_text)
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"\n채팅 루프 중 오류 발생: {e}")

        print("클라이언트를 종료합니다.")

    async def cleanup(self):
        """모든 MCP 연결 및 리소스 정리"""
        print("\n리소스 정리 중...")
        # AsyncExitStack이 관리하는 모든 컨텍스트(stdio_client, sse_client, ClientSession)를 닫음
        await self.exit_stack.aclose()
        print("클라이언트 종료됨.")
