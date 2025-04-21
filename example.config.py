import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Google Generative AI 설정 ---

# 여기에 Google API 키를 입력하세요.
# 보안을 위해 이 파일은 .gitignore에 추가하는 것이 좋습니다.
GOOGLE_API_KEY = ""

# 사용할 AI 모델 이름
# 사용 가능한 모델: 'gemini-2.0-flash-latest' 등
MODEL_NAME = 'gemini-2.5-flash-preview-04-17'

# AI 모델 안전 설정
# 각 카테고리에 대한 차단 임계값을 설정합니다.
# 사용 가능한 값: HarmBlockThreshold.BLOCK_NONE, HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
#                HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE, HarmBlockThreshold.BLOCK_ONLY_HIGH
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

# --- 기타 설정 (필요시 추가) ---
# 예: 명령어 실행 타임아웃
COMMAND_TIMEOUT = 30 # 초 단위