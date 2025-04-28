import os
import json
import traceback
import google.genai as genai
from dotenv import load_dotenv

NO_PROMPT_OPTION = ""


def load_config():
    """
    환경 변수와 설정 파일에서 애플리케이션 설정을 로드하고 검증합니다.

    Returns:
        dict: 로드된 설정 값들을 담은 딕셔너리. 오류 발생 시 None 반환.
              딕셔너리 키: 'google_api_key', 'model_name', 'safety_settings',
                        'generation_config', 'mcp_servers', 'whisper_model_name',
                        'whisper_device_pref', 'stt_provider', 'google_credentials'
    """
    config = {}
    try:
        load_dotenv()

        # Google API Key
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key or google_api_key == "YOUR_API_KEY_HERE":
            raise ValueError(
                "환경 변수 'GOOGLE_API_KEY'가 설정되지 않았거나 유효하지 않습니다. .env 파일을 확인하세요."
            )
        # API 키 유효성 검증 (실제 클라이언트 생성 시도)
        try:
            genai.Client(api_key=google_api_key)
        except Exception as api_err:
            raise ValueError(f"Google API 키가 유효하지 않습니다: {api_err}")
        config["google_api_key"] = google_api_key

        # Model Name
        model_name = os.getenv("MODEL_NAME")
        if not model_name:
            print(
                "경고: 환경 변수 'MODEL_NAME'이 설정되지 않았습니다. 기본값 'gemini-2.5-flash-preview-04-17'를 사용합니다."
            )
            model_name = "gemini-2.5-flash-preview-04-17"
        config["model_name"] = model_name

        # Safety Settings
        safety_settings_str = os.getenv("SAFETY_SETTINGS")
        safety_settings = None
        if safety_settings_str:
            try:
                safety_settings_list_of_dicts = json.loads(safety_settings_str)
                if not isinstance(safety_settings_list_of_dicts, list):
                    raise ValueError(
                        "SAFETY_SETTINGS 형식이 잘못되었습니다. JSON 리스트 형식이어야 합니다."
                    )
                safety_settings = safety_settings_list_of_dicts
            except json.JSONDecodeError:
                raise ValueError(
                    "환경 변수 'SAFETY_SETTINGS'를 JSON으로 파싱할 수 없습니다. 형식을 확인하세요."
                )
            except Exception as e:
                raise ValueError(f"SAFETY_SETTINGS 처리 중 오류: {e}")
        else:
            print(
                "경고: 환경 변수 'SAFETY_SETTINGS'가 설정되지 않았습니다. 기본적인 안전 설정을 사용합니다."
            )
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ]
        config["safety_settings"] = safety_settings

        # Generation Config
        generation_config_str = os.getenv("GENERATION_CONFIG")
        generation_config = None
        if generation_config_str:
            try:
                generation_config_dict = json.loads(generation_config_str)
                if not isinstance(generation_config_dict, dict):
                    raise ValueError(
                        "GENERATION_CONFIG 형식이 잘못되었습니다. JSON 객체 형식이어야 합니다."
                    )
                generation_config = generation_config_dict
            except json.JSONDecodeError:
                raise ValueError(
                    "환경 변수 'GENERATION_CONFIG'를 JSON으로 파싱할 수 없습니다."
                )
            except Exception as e:
                raise ValueError(f"GENERATION_CONFIG 처리 중 오류: {e}")
        config["generation_config"] = generation_config

        # MCP Config
        mcp_config_path = "mcp_config.json"
        if not os.path.exists(mcp_config_path):
            raise FileNotFoundError(
                f"MCP 설정 파일 '{mcp_config_path}'을 찾을 수 없습니다."
            )
        with open(mcp_config_path, "r") as f:
            mcp_config_data = json.load(f)
            mcp_servers = mcp_config_data.get("mcpServers")
            if not mcp_servers or not isinstance(mcp_servers, dict):
                raise ValueError(
                    f"'{mcp_config_path}' 파일에 'mcpServers' 객체가 없거나 형식이 잘못되었습니다."
                )
        config["mcp_servers"] = mcp_servers

        # Whisper Model Name
        whisper_model_name = os.getenv("WHISPER_MODEL", "base")
        if whisper_model_name == "base":
            print(
                "경고: 환경 변수 'WHISPER_MODEL'이 설정되지 않았습니다. 기본값 'base' 모델을 사용합니다."
            )
        else:
            print(
                f"환경 변수 'WHISPER_MODEL'에서 '{whisper_model_name}' 모델을 사용합니다."
            )
        config["whisper_model_name"] = whisper_model_name

        # Whisper Device Preference
        whisper_device_pref = os.getenv("WHISPER_DEVICE", "auto").lower()
        if whisper_device_pref not in ["auto", "cpu", "mps", "cuda"]:
            print(
                f"경고: WHISPER_DEVICE 환경 변수 값 '{whisper_device_pref}'이(가) 유효하지 않습니다. 'auto' 설정을 사용합니다."
            )
            whisper_device_pref = "auto"
        else:
            print(f"환경 변수 'WHISPER_DEVICE' 설정: '{whisper_device_pref}'")
        config["whisper_device_pref"] = whisper_device_pref

        # STT Provider
        stt_provider = os.getenv("STT_PROVIDER", "whisper").lower()
        if stt_provider not in ["whisper", "google"]:
            print(
                f"경고: STT_PROVIDER 환경 변수 값 '{stt_provider}'이(가) 유효하지 않습니다. 'whisper' 설정을 사용합니다."
            )
            stt_provider = "whisper"
        print(f"사용할 STT 제공자: '{stt_provider}'")
        config["stt_provider"] = stt_provider

        # Google Cloud Credentials (for STT)
        google_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if stt_provider == "google":
            if not google_credentials:
                print(
                    "\n경고: STT_PROVIDER가 'google'로 설정되었지만 GOOGLE_APPLICATION_CREDENTIALS 환경 변수가 설정되지 않았습니다."
                )
                print(
                    "Google Cloud 인증에 실패할 수 있습니다. .env 파일을 확인하세요.\n"
                )
            elif not os.path.exists(google_credentials):
                print(
                    f"\n경고: GOOGLE_APPLICATION_CREDENTIALS 경로 '{google_credentials}'에 파일이 존재하지 않습니다."
                )
                print("Google Cloud 인증에 실패할 수 있습니다.\n")
            else:
                print(f"Google Cloud 인증 파일 경로: '{google_credentials}'")
        config["google_credentials"] = google_credentials

        return config

    except (ValueError, FileNotFoundError) as e:
        print(f"오류: 설정 로드 실패 - {e}")
        return None
    except Exception as e:
        print(f"설정 중 예기치 않은 오류 발생: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    loaded_config = load_config()
    if loaded_config:
        print("\n--- 설정 로드 성공 ---")
        for key, value in loaded_config.items():
            if key == "google_api_key":
                print(f"{key}: {'*' * 10}")
            else:
                print(f"{key}: {value}")
        print("---------------------\n")
    else:
        print("\n--- 설정 로드 실패 ---")
