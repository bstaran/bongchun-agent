import asyncio
import os
import json
import traceback
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from PIL import Image, UnidentifiedImageError


from mcp import ClientSession, StdioServerParameters, types as mcp_types
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

import google.genai as genai
from google.genai import types
from google.genai.types import Tool, FunctionDeclaration, GenerationConfig

from google.genai.types import FunctionResponse


class MultiMCPClient:
    def __init__(
        self,
        model_name: str = "gemini-2.0-flash-latest",
        safety_settings: Optional[List[Dict[str, Any]]] = None,
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
    ):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.all_mcp_tools: List[mcp_types.Tool] = []
        self.tool_to_server_map: Dict[str, str] = {}

        try:
            self.gemini_client = genai.Client()
            print(f"✅ Gemini 클라이언트 초기화 완료.")
            self.model_name = model_name
            self.safety_settings = safety_settings
            self.generation_config = generation_config
            self.system_instruction = system_instruction
            self.chat_session = self.gemini_client.chats.create(
                model=f"models/{self.model_name}",
                history=[],
            )
            print(
                f"✅ Gemini 채팅 세션 시작 완료 (모델: {self.model_name}). 시스템 프롬프트는 chats.create에서 직접 지원되지 않습니다."
            )

        except AttributeError as ae:
            print(f"❌ Gemini 클라이언트 생성 중 속성 오류 발생: {ae}")
            print("   google-generativeai 라이브러리가 최신 버전인지 확인하세요.")
            raise
        except TypeError as te:
            print(f"❌ Gemini 채팅 세션 생성 중 타입 오류 발생: {te}")
            print(
                "   chats.create() 호출 시 지원되지 않는 인자가 사용되었을 수 있습니다."
            )
            raise
        except Exception as e:
            print(f"❌ Gemini 클라이언트 또는 채팅 세션 초기화 실패: {e}")
            traceback.print_exc()
            raise

    def start_new_chat(self):
        """
        현재 채팅 세션의 기록을 초기화하고 새 세션을 시작합니다.
        기존의 시스템 프롬프트는 유지됩니다.
        """
        try:
            self.chat_session = self.gemini_client.chats.create(
                model=f"models/{self.model_name}",
                history=[],
            )
            print("새 채팅 세션 시작됨 (대화 기록 초기화).")
            return True
        except TypeError as te:
            print(f"❌ 새 채팅 세션 시작 실패 (타입 오류): {te}")
            return False
        except Exception as e:
            print(f"❌ 새 채팅 세션 시작 실패: {e}")
            traceback.print_exc()
            return False

    def _clean_schema_for_gemini(
        self, schema: Optional[Dict[str, Any]], tool_name: str, path: str = "root"
    ) -> Optional[Dict[str, Any]]:
        """Gemini FunctionDeclaration 스키마에 맞게 불필요한 필드를 제거하는 재귀 함수"""
        if not isinstance(schema, dict):
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
            valid_enum = [
                val for val in enum_values if isinstance(val, (str, int, float, bool))
            ]
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
                    cleaned_prop = self._clean_schema_for_gemini(
                        prop_schema, tool_name, f"{path}.properties.{prop_name}"
                    )
                    if cleaned_prop:
                        cleaned_properties[prop_name] = cleaned_prop
                if cleaned_properties:
                    cleaned_schema["properties"] = cleaned_properties

            # 5. required 처리 (type이 'object'이고 properties가 있을 때)
            if "properties" in cleaned_schema:
                required = schema.get("required")
                if isinstance(required, list):
                    valid_required = [
                        req
                        for req in required
                        if isinstance(req, str) and req in cleaned_schema["properties"]
                    ]
                    if valid_required:
                        cleaned_schema["required"] = valid_required

        # 6. items 처리 (type이 'array'일 때)
        elif current_type == "array":
            items_schema = schema.get("items")
            cleaned_items = self._clean_schema_for_gemini(
                items_schema, tool_name, f"{path}.items"
            )
            if cleaned_items:
                cleaned_schema["items"] = cleaned_items
            else:
                print(
                    f"경고 [{tool_name}]: 스키마 경로 '{path}' (배열 타입)에 유효한 'items' 정의가 없습니다."
                )

        return cleaned_schema if cleaned_schema else None

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
                cleaned_parameters = self._clean_schema_for_gemini(
                    tool.inputSchema, tool.name
                )

                func_decl = FunctionDeclaration(
                    name=tool.name,
                    description=(
                        str(tool.description)
                        if not isinstance(tool.description, str)
                        else tool.description
                    ),
                    parameters=cleaned_parameters if cleaned_parameters else None,
                )
                gemini_function_declarations.append(func_decl)
            except Exception as e:
                print(f"오류: 도구 '{tool.name}'의 FunctionDeclaration 생성 실패 - {e}")

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
        env = config.get("env", os.environ.copy())
        if not command:
            print(f"경고: 서버 '{server_name}' 설정에 'command'가 없어 건너뜁니다.")
            return

        server_params = StdioServerParameters(command=command, args=args, env=env)
        try:
            print(f"'{server_name}' (stdio) 연결 시도: {command} {' '.join(args)}")
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

            list_tools_result = await session.list_tools()
            server_tools = list_tools_result.tools if list_tools_result else []
            print(f"  '{server_name}' 제공 도구: {[t.name for t in server_tools]}")
            self.all_mcp_tools.extend(server_tools)
            for tool in server_tools:
                if tool.name in self.tool_to_server_map:
                    print(
                        f"경고: 도구 이름 '{tool.name}'이(가) '{self.tool_to_server_map[tool.name]}' 서버와 '{server_name}' 서버에 중복됩니다. '{server_name}'의 도구를 사용합니다."
                    )
                self.tool_to_server_map[tool.name] = server_name

        except Exception as e:
            print(f"❌ '{server_name}' 서버 연결 또는 초기화 실패: {e}")

    async def _connect_and_init_sse(self, server_name: str, config: Dict[str, Any]):
        """지정된 SSE 서버에 연결하고 초기화하는 내부 함수"""
        url = config.get("url")
        headers = config.get("headers")
        if not url:
            print(f"경고: SSE 서버 '{server_name}' 설정에 'url'이 없어 건너뜁니다.")
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
            transport_type = config.get("transport", "stdio").lower()

            if transport_type == "stdio":
                if "command" in config:
                    tasks.append(self._connect_and_init_stdio(server_name, config))
                else:
                    print(
                        f"경고: stdio 서버 '{server_name}' 설정에 'command'가 없어 건너뜁니다."
                    )
            elif transport_type == "sse":
                if "url" in config:
                    tasks.append(self._connect_and_init_sse(server_name, config))
                else:
                    print(
                        f"경고: SSE 서버 '{server_name}' 설정에 'url'이 없어 건너뜁니다."
                    )
            # TODO: WebSocket 등 다른 전송 방식 지원 추가
            else:
                print(
                    f"경고: 지원되지 않는 전송 방식 '{transport_type}' (서버: {server_name}). 건너뜁니다."
                )

        await asyncio.gather(*tasks)
        print(
            f"\n총 {len(self.sessions)}개의 서버에 성공적으로 연결 및 초기화되었습니다."
        )

    async def process_query(
        self,
        query: str,
        additional_prompt: Optional[str] = None,
        file_paths: Optional[List[str]] = None,
    ) -> str:
        """
        사용자 쿼리와 선택적 파일 첨부(들), 추가 프롬프트를 처리하고, 필요시 MCP 도구를 호출합니다.
        additional_prompt가 제공되면 쿼리 앞에 추가됩니다.
        file_paths 리스트가 제공되고 첫 번째 파일이 이미지 파일이면 멀티모달 요청으로 처리합니다. (현재는 첫 파일만 지원)
        기본 시스템 프롬프트는 세션 생성 시 적용됩니다.
        """
        if not self.sessions:
            print("경고: 연결된 MCP 서버가 없습니다. 도구 사용이 제한됩니다.")
        if not hasattr(self, "chat_session"):
            return "오류: Gemini 모델이 초기화되지 않았습니다."

        try:
            full_query = query
            if additional_prompt:
                full_query = f"{additional_prompt}\n\n---\n\nUser Request:\n{query}"
                print(
                    f"\n[DEBUG] Combined query with additional prompt:\n{full_query[:200]}..."
                )
            else:
                print("\n[DEBUG] Processing query without additional prompt content.")

            print("\nGemini 모델에게 요청 전송 중...")
            gemini_tools = self._mcp_tools_to_gemini_tools()

            image_part = None
            mime_type = None
            first_file_path = file_paths[0] if file_paths else None
            print(
                f"[DEBUG] 이미지 처리 시작. first_file_path: {first_file_path}, Pillow 사용 가능: {bool(Image)}"
            )
            if first_file_path and Image:
                try:
                    p = Path(first_file_path)
                    print(f"[DEBUG] 파일 경로 객체 생성: {p}")
                    if p.is_file():
                        print(f"[DEBUG] 파일 존재 확인: {first_file_path}")
                        mime_type, _ = mimetypes.guess_type(p)
                        print(
                            f"[DEBUG] MIME 타입 확인: {mime_type} for {first_file_path}"
                        )
                        if mime_type and mime_type.startswith("image/"):
                            print(f"[DEBUG] 이미지 파일 MIME 타입 확인됨: {mime_type}")
                            try:
                                print(
                                    f"[DEBUG] Pillow로 이미지 열기 시도: {first_file_path}"
                                )
                                img = Image.open(p)
                                img.verify()
                                img.close()
                                img = Image.open(p)
                                print(
                                    f"[DEBUG] Pillow로 이미지 열기 성공: {first_file_path}, Format: {img.format}, Size: {img.size}"
                                )
                                img.close()
                            except UnidentifiedImageError:
                                print(
                                    f"[DEBUG] 오류: Pillow가 이미지 파일을 식별할 수 없음: {first_file_path}"
                                )
                                raise
                            except Exception as img_err:
                                print(
                                    f"[DEBUG] 오류: Pillow 이미지 처리 중 오류 발생: {img_err}"
                                )
                                raise

                            try:
                                print(
                                    f"[DEBUG] types.Part.from_data 생성 시도: {first_file_path}"
                                )
                                image_part = types.Part.from_bytes(
                                    mime_type=mime_type,
                                    data=p.read_bytes(),
                                )
                                print(
                                    f"[DEBUG] types.Part.from_bytes 생성 성공. MimeType: {mime_type}, Data Length: {len(image_part.data) if hasattr(image_part, 'data') else 'N/A'}"
                                )
                            except Exception as part_err:
                                print(
                                    f"[DEBUG] 오류: types.Part.from_data 생성 중 오류 발생: {part_err}"
                                )
                                raise

                            print(
                                "[DEBUG] 이미지 데이터를 Gemini 요청에 포함 준비 완료."
                            )
                        else:
                            print(
                                f"[DEBUG] 경고: 첨부된 파일 '{first_file_path}'은(는) 이미지 파일이 아닙니다 (MIME: {mime_type}). 텍스트 요청만 보냅니다."
                            )
                    else:
                        print(
                            f"[DEBUG] 경고: 첨부된 파일 경로 '{first_file_path}'을(를) 찾을 수 없거나 파일이 아닙니다."
                        )
                except FileNotFoundError:
                    print(
                        f"[DEBUG] 오류: 첨부된 이미지 파일 '{first_file_path}'을(를) 찾을 수 없습니다."
                    )
                    return (
                        f"오류: 첨부 파일 '{first_file_path}'을(를) 찾을 수 없습니다."
                    )
                except UnidentifiedImageError:
                    print(
                        f"[DEBUG] 오류 처리: UnidentifiedImageError for {first_file_path}"
                    )
                    return f"오류: 첨부 파일 '{first_file_path}'은(는) 유효한 이미지 파일이 아닙니다."
                except IOError as e:
                    print(f"[DEBUG] 오류 처리: IOError for {first_file_path}: {e}")
                    return (
                        f"오류: 첨부 파일 '{first_file_path}' 처리 중 IO 오류 발생: {e}"
                    )
                except Exception as e:
                    print(
                        f"[DEBUG] 오류 처리: 예기치 않은 이미지 처리 오류 for {first_file_path}: {e}"
                    )
                    traceback.print_exc()
                    return f"오류: 첨부 파일 처리 중 예기치 않은 오류 발생: {e}"
            elif first_file_path and not Image:
                print(
                    "[DEBUG] 경고: Pillow 라이브러리가 없어 이미지 파일을 처리할 수 없습니다. 텍스트 요청만 보냅니다."
                )
            else:
                print(
                    "[DEBUG] 이미지 파일 경로가 제공되지 않았거나 Pillow 라이브러리가 없습니다. 이미지 처리 건너뜁니다."
                )

            request_content_parts = [full_query]
            log_data_items = [{"type": "text", "content": full_query}]

            if image_part:
                print("[DEBUG] Sending multimodal request (text + image)")
                request_content_parts.append(image_part)
                log_data_items.append(
                    {
                        "type": "image",
                        "mime_type": mime_type,
                        "data_length": (
                            len(image_part.data)
                            if hasattr(image_part, "data")
                            else "N/A"
                        ),
                    }
                )
            else:
                print("[DEBUG] Sending text-only request")

            print(
                f"API 요청 데이터: {json.dumps(log_data_items, indent=2, ensure_ascii=False)}"
            )

            send_args = {}

            print(
                f"[DEBUG] Preparing arguments for send_message (should be empty): {send_args}"
            )

            response = self.chat_session.send_message(
                request_content_parts,
                **send_args,
            )

            final_text_parts = []
            while True:
                if not response.candidates:
                    print("경고: Gemini로부터 응답 후보를 받지 못했습니다.")
                    break

                candidate_content = response.candidates[0].content
                if not candidate_content or not candidate_content.parts:
                    print("경고: Gemini 응답에 내용(content or parts)이 없습니다.")
                    if final_text_parts:
                        break
                    else:
                        return "오류: AI로부터 유효한 응답을 받지 못했습니다."

                latest_response_part = candidate_content.parts[0]

                if hasattr(latest_response_part, "text") and latest_response_part.text:
                    final_text_parts.append(latest_response_part.text)
                    break

                elif (
                    hasattr(latest_response_part, "function_call")
                    and latest_response_part.function_call
                ):
                    function_call = latest_response_part.function_call
                    tool_name = function_call.name

                    target_server_name = self.tool_to_server_map.get(tool_name)
                    if not target_server_name:
                        print(
                            f"❌ 오류: Gemini가 알 수 없는 도구 '{tool_name}' 호출을 시도했습니다."
                        )
                        response = self.chat_session.send_message(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={
                                    "content": f"Error: Tool '{tool_name}' not found or not configured correctly."
                                },
                            ),
                            tools=gemini_tools,
                        )
                        continue

                    target_session = self.sessions.get(target_server_name)
                    if not target_session:
                        print(
                            f"❌ 오류: 도구 '{tool_name}'을 처리할 서버 '{target_server_name}'의 세션을 찾을 수 없습니다."
                        )
                        response = self.chat_session.send_message(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={
                                    "content": f"Error: Could not find active session for server '{target_server_name}' required by tool '{tool_name}'."
                                },
                            ),
                            tools=gemini_tools,
                        )
                        continue

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

                    try:
                        print(
                            f"[DEBUG] Calling MCP tool '{tool_name}' on server '{target_server_name}' with args: {tool_args_dict}"
                        )
                        mcp_result = await target_session.call_tool(
                            tool_name, arguments=tool_args_dict
                        )
                        print(f"[DEBUG] MCP tool '{tool_name}' result: {mcp_result}")

                        result_content = (
                            "[Tool executed successfully, no specific content returned]"
                        )
                        if mcp_result.isError:
                            result_content = f"[Error executing tool '{tool_name}': {mcp_result.error.message if mcp_result.error else 'Unknown error'}]"
                            print(
                                f"MCP 도구 '{tool_name}' 실행 오류 보고됨: {result_content}"
                            )
                        elif mcp_result.content:
                            text_contents = [
                                c.text
                                for c in mcp_result.content
                                if isinstance(c, mcp_types.TextContent)
                            ]
                            if text_contents:
                                result_content = "\n".join(text_contents)
                                print(
                                    f"[MCP 도구 '{tool_name}' 결과]: {result_content[:200]}{'...' if len(result_content) > 200 else ''}"
                                )
                            else:
                                json_contents = [
                                    c.model_dump_json()
                                    for c in mcp_result.content
                                    if isinstance(c, mcp_types.JsonContent)
                                ]
                                if json_contents:
                                    result_content = json.dumps(json_contents)
                                    print(
                                        f"[MCP 도구 '{tool_name}' JSON 결과]: {result_content[:200]}{'...' if len(result_content) > 200 else ''}"
                                    )
                                else:
                                    result_content = f"[MCP 도구 '{tool_name}' 결과 type: {type(mcp_result.content[0])}]"
                                    print(result_content)

                        function_response_payload = FunctionResponse(
                            name=tool_name,
                            response={"content": result_content},
                        )
                        print(
                            f"[DEBUG] Sending FunctionResponse to Gemini: {function_response_payload}"
                        )
                        response = self.chat_session.send_message(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={"content": result_content},
                            ),
                            tools=gemini_tools,
                        )
                        print(
                            f"[DEBUG] Response from Gemini after sending FunctionResponse: {response.candidates[0].content.parts[0] if response.candidates else 'No candidates'}"
                        )
                        continue

                    except Exception as tool_error:
                        print(
                            f"❌ ERROR during MCP tool '{tool_name}' execution: {tool_error}"
                        )
                        traceback.print_exc()
                        error_response_payload = FunctionResponse(
                            name=tool_name,
                            response={
                                "content": f"Error: Exception during tool execution: {tool_error}"
                            },
                        )
                        print(
                            f"[DEBUG] Sending ERROR FunctionResponse to Gemini: {error_response_payload}"
                        )
                        response = self.chat_session.send_message(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={
                                    "content": f"Error: Exception during tool execution: {tool_error}"
                                },
                            ),
                            tools=gemini_tools,
                        )
                        print(
                            f"[DEBUG] Response from Gemini after sending ERROR FunctionResponse: {response.candidates[0].content.parts[0] if response.candidates else 'No candidates'}"
                        )
                        continue
                else:
                    print(
                        f"경고: Gemini로부터 예상치 못한 응답 형식을 받았습니다: {latest_response_part}"
                    )
                    if final_text_parts:
                        break
                    else:
                        return f"오류: AI로부터 예상치 못한 응답 형식 수신: {latest_response_part}"

            return "\n".join(final_text_parts)

        except Exception as e:
            print(f"Gemini API 호출 중 오류 발생: {e}")
            traceback.print_exc()
            return f"오류: AI 모델과 통신 중 문제가 발생했습니다 - {e}"

    async def cleanup(self):
        """모든 MCP 연결 및 리소스 정리"""
        print("\n리소스 정리 중...")
        await self.exit_stack.aclose()
        print("클라이언트 종료됨.")
