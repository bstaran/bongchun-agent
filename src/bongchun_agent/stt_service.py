import sys
import os
import threading
import queue
import time
import traceback
import io
import wave

import torch

try:
    from faster_whisper import WhisperModel
    import sounddevice as sd
    import numpy as np
except ImportError as e:
    print(f"오류: Whisper STT 서비스에 필요한 라이브러리를 찾을 수 없습니다 ({e}).")
    print("다음 명령어를 실행하여 설치하세요:")
    print("uv add faster-whisper sounddevice numpy torch")

try:
    from google.cloud import speech
except ImportError:
    print("경고: Google Cloud Speech 라이브러리를 찾을 수 없습니다.")
    print("Google STT를 사용하려면 다음 명령어를 실행하여 설치하세요:")
    print("uv add google-cloud-speech")
    speech = None

SAMPLE_RATE = 16000
RECORD_SECONDS = 10
SILENCE_THRESHOLD = 500
SILENCE_DURATION = 1.5


class STTService:
    """
    Whisper 또는 Google Cloud를 이용한 음성-텍스트 변환 서비스 클래스
    """

    def __init__(
        self,
        provider="whisper",
        whisper_model_name="base",
        whisper_device_preference="auto",
        google_lang_code="ko-KR",
    ):
        """
        서비스 초기화 및 선택된 STT 제공자 설정
        Args:
            provider (str): 사용할 STT 제공자 ('whisper' 또는 'google')
            whisper_model_name (str): Whisper 사용 시 모델 이름 또는 경로
            whisper_device_preference (str): Whisper 사용 시 장치 설정 ('auto', 'cpu', 'mps')
            google_lang_code (str): Google Cloud STT 사용 시 언어 코드
        """
        self.provider = provider
        self.audio_queue = queue.Queue()
        self.stop_recording_event = threading.Event()

        self.whisper_model = None
        self.whisper_device = None
        self.google_client = None
        self.google_lang_code = google_lang_code

        if self.provider == "whisper":
            self.whisper_model_name = whisper_model_name
            self.whisper_device_preference = whisper_device_preference
            self._load_whisper_model()
        elif self.provider == "google":
            if speech is None:
                raise RuntimeError(
                    "Google Cloud Speech 라이브러리가 설치되지 않았습니다."
                )
            try:
                print("Google Cloud Speech 클라이언트 초기화 중...")
                self.google_client = speech.SpeechClient()
                print("Google Cloud Speech 클라이언트 초기화 완료.")
            except Exception as e:
                print(f"Google Cloud Speech 클라이언트 초기화 실패: {e}")
                traceback.print_exc()
                raise RuntimeError("Google Cloud Speech 클라이언트 초기화 실패") from e
        else:
            raise ValueError(f"지원하지 않는 STT 제공자: {provider}")

    def _load_whisper_model(self):
        """Whisper 모델 로드 (사용자 설정 또는 자동 감지 기반)"""
        if "WhisperModel" not in globals():
            raise RuntimeError("Faster Whisper 라이브러리가 로드되지 않았습니다.")

        print(
            f"Whisper 모델 '{self.whisper_model_name}' 로드 중 (선호 장치: {self.whisper_device_preference})..."
        )
        device = "cpu"

        if self.device_preference == "cpu":
            print("사용자 설정에 따라 CPU를 사용합니다.")
            device = "cpu"
        elif self.device_preference == "mps":
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                print("사용자 설정 'mps' 확인됨. MPS (Apple Silicon GPU)를 사용합니다.")
                device = "mps"
            else:
                print(
                    "경고: 사용자 설정 'mps'이지만 MPS를 사용할 수 없습니다. CPU로 fallback합니다."
                )
                device = "cpu"
        elif self.device_preference == "auto":
            # 자동 감지 로직 (MPS 우선)
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                print(
                    "자동 감지: MPS (Apple Silicon GPU) 사용 가능. 장치를 'mps'로 설정합니다."
                )
                device = "mps"
            #     device = "cuda"
            else:
                print("자동 감지: MPS/CUDA 사용 불가. CPU를 사용합니다.")
                device = "cpu"

        print(
            f"실제 WhisperModel 로드 시도 모델: '{self.model_name}', 장치: '{device}'"
        )
        try:
            self.whisper_model = WhisperModel(
                self.whisper_model_name,
                device=device,
                compute_type="int8",
                download_root="../models",
            )
            self.whisper_device = device

            print(f"Whisper 모델 로드 완료 (사용 장치: {self.whisper_device}).")
        except Exception as e:
            print(f"Whisper 모델 로드 중 심각한 오류 발생: {e}")
            traceback.print_exc()
            raise RuntimeError(
                f"Whisper 모델 '{self.whisper_model_name}' 로드 실패"
            ) from e

    def _audio_callback(self, indata, frames, time, status):
        """사운드 장치에서 호출되는 콜백 함수"""
        if status:
            print(f"오디오 콜백 상태: {status}", file=sys.stderr)
        self.audio_queue.put(indata.copy())

    def record_audio(self):
        """
        마이크에서 오디오를 녹음하고 NumPy 배열로 반환.
        침묵 또는 최대 녹음 시간에 도달하면 자동으로 중지됩니다.
        이 함수는 동기적으로 실행되므로 별도 스레드에서 호출해야 합니다.
        """
        self.audio_queue = queue.Queue()
        self.stop_recording_event.clear()

        print(
            f"\n🎤 {RECORD_SECONDS}초 동안 또는 {SILENCE_DURATION}초 침묵 시 녹음 시작..."
        )
        print(
            "(녹음을 중단하려면 Ctrl+C를 누르세요 - 터미널에 따라 동작이 다를 수 있음)"
        )

        stream = None
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                callback=self._audio_callback,
                blocksize=int(SAMPLE_RATE * 0.1),
            )
            stream.start()

            recorded_frames = []
            silent_frames = 0
            total_frames = 0
            frames_per_second = SAMPLE_RATE
            silence_limit = int(SILENCE_DURATION * frames_per_second)
            max_frames = int(RECORD_SECONDS * frames_per_second)
            last_sound_time = time.time()

            while not self.stop_recording_event.is_set():
                try:
                    frame = self.audio_queue.get(timeout=0.1)
                    recorded_frames.append(frame)
                    current_frames = len(frame)
                    total_frames += current_frames

                    rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
                    if rms < SILENCE_THRESHOLD:
                        if time.time() - last_sound_time > SILENCE_DURATION:
                            print("녹음 중지 (침묵 감지).")
                            break
                    else:
                        last_sound_time = time.time()
                        silent_frames = 0

                    if total_frames >= max_frames:
                        print("녹음 중지 (최대 시간 도달).")
                        break

                except queue.Empty:
                    if time.time() - last_sound_time > SILENCE_DURATION:
                        print("녹음 중지 (타임아웃 후 침묵 감지).")
                        break
                    if total_frames >= max_frames:
                        print("녹음 중지 (시간 초과).")
                        break
                    if self.stop_recording_event.is_set():
                        print("녹음 중지 (외부 요청).")
                        break
                    continue
                except Exception as e:
                    print(f"녹음 루프 중 오류: {e}")
                    traceback.print_exc()
                    self.stop_recording_event.set()
                    break

        except sd.PortAudioError as pae:
            print(f"오디오 장치 오류: {pae}")
            print("사용 가능한 오디오 입력 장치가 있는지 확인하세요.")
            return None
        except Exception as e:
            print(f"녹음 스트림 시작 중 오류: {e}")
            traceback.print_exc()
            return None
        finally:
            if stream is not None:
                try:
                    if stream.active:
                        stream.stop()
                    stream.close()
                except Exception as e:
                    print(f"오디오 스트림 정리 중 오류: {e}")
            print("녹음 완료.")

        if not recorded_frames:
            print("녹음된 데이터가 없습니다.")
            return None

        try:
            audio_data = np.concatenate(recorded_frames, axis=0)
            audio_float32 = audio_data.flatten().astype(np.float32) / 32768.0
            return audio_float32
        except Exception as e:
            print(f"녹음 데이터 처리 중 오류: {e}")
            traceback.print_exc()
            return None

    def _numpy_to_wav_bytes(self, audio_data_np: np.ndarray) -> bytes:
        """NumPy float32 오디오 데이터를 WAV 형식의 바이트 스트림으로 변환"""
        if audio_data_np is None or audio_data_np.size == 0:
            return b""
        # float32 [-1.0, 1.0] -> int16 [-32768, 32767]
        audio_data_int16 = (audio_data_np * 32767).astype(np.int16)

        bytes_io = io.BytesIO()
        with wave.open(bytes_io, "wb") as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data_int16.tobytes())
        return bytes_io.getvalue()

    def transcribe_audio(self, audio_data_np: np.ndarray) -> str:
        """
        선택된 STT 제공자를 사용하여 오디오 데이터를 텍스트로 변환.
        Args:
            audio_data_np (np.ndarray): float32 형식의 NumPy 오디오 데이터
        Returns:
            str: 변환된 텍스트
        """
        if audio_data_np is None or audio_data_np.size == 0:
            print("변환할 오디오 데이터가 없습니다.")
            return ""

        if self.provider == "whisper":
            return self._transcribe_whisper(audio_data_np)
        elif self.provider == "google":
            return self._transcribe_google(audio_data_np)
        else:
            print(f"오류: 알 수 없는 STT 제공자 '{self.provider}'")
            return ""

    def _transcribe_whisper(self, audio_data_np: np.ndarray) -> str:
        """Whisper를 사용하여 변환"""
        if self.whisper_model is None:
            print("오류: Whisper 모델이 로드되지 않았습니다.")
            return ""
        print(f"Whisper로 음성 변환 중 (장치: {self.whisper_device})...")
        try:
            segments, _info = self.whisper_model.transcribe(
                audio_data_np, language="ko"
            )
            transcribed_text = "".join(segment.text for segment in segments).strip()
            print("Whisper 변환 완료.")
            return transcribed_text
        except Exception as e:
            print(f"Whisper 변환 중 오류 발생: {e}")
            traceback.print_exc()
            return ""

    def _transcribe_google(self, audio_data_np: np.ndarray) -> str:
        """Google Cloud Speech를 사용하여 변환"""
        if self.google_client is None:
            print("오류: Google Cloud Speech 클라이언트가 초기화되지 않았습니다.")
            return ""

        print(f"Google Cloud STT로 음성 변환 중 (언어: {self.google_lang_code})...")
        try:
            audio_bytes = self._numpy_to_wav_bytes(audio_data_np)
            if not audio_bytes:
                print("오류: 오디오 데이터를 WAV 바이트로 변환 실패.")
                return ""

            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=SAMPLE_RATE,
                language_code=self.google_lang_code,
            )

            response = self.google_client.recognize(config=config, audio=audio)

            if response.results:
                transcribed_text = (
                    response.results[0].alternatives[0].transcript.strip()
                )
                print("Google Cloud STT 변환 완료.")
                return transcribed_text
            else:
                print("Google Cloud STT 결과 없음.")
                return ""
        except Exception as e:
            print(f"Google Cloud STT 변환 중 오류 발생: {e}")
            traceback.print_exc()
            return ""

    def stop_recording(self):
        """외부에서 녹음을 중지시킬 때 호출"""
        print("녹음 중지 요청 수신.")
        self.stop_recording_event.set()


async def test_stt_service():
    """stt_service.py 단독 실행 시 테스트 함수"""
    print("STT 서비스 테스트 시작...")
    test_provider = os.getenv("STT_PROVIDER", "whisper").lower()
    print(f"테스트할 STT 제공자: {test_provider}")

    if test_provider == "google" and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print(
            "\n경고: Google STT 테스트를 위해 GOOGLE_APPLICATION_CREDENTIALS 환경 변수를 설정해야 합니다."
        )
        print("테스트를 건너뜁니다.\n")
        return
    elif test_provider == "google" and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        if not os.path.exists(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")):
            print(
                f"\n경고: GOOGLE_APPLICATION_CREDENTIALS 경로 '{os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}'에 파일이 없습니다."
            )
            print("Google STT 테스트를 건너뜁니다.\n")
            return

    try:
        stt = STTService(
            provider=test_provider,
            whisper_model_name=os.getenv("WHISPER_MODEL", "base"),
            whisper_device_preference=os.getenv("WHISPER_DEVICE", "auto"),
        )

        print("\n--- 녹음 테스트 ---")
        audio_np = await asyncio.to_thread(stt.record_audio)

        if audio_np is not None:
            print(f"녹음된 오디오 데이터 길이: {len(audio_np)} 샘플")
            print("\n--- 변환 테스트 ---")
            text = await asyncio.to_thread(stt.transcribe_audio, audio_np)
            print(f"\n변환된 텍스트 ({stt.provider}): '{text}'")
        else:
            print("녹음에 실패하여 변환 테스트를 건너뜁니다.")

    except RuntimeError as e:
        print(f"STT 서비스 ({test_provider}) 초기화 또는 테스트 실패: {e}")
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        traceback.print_exc()

    print("\nSTT 서비스 테스트 종료.")


if __name__ == "__main__":
    try:
        asyncio.run(test_stt_service())
    except KeyboardInterrupt:
        print("\n테스트 중단됨.")
    except Exception as e:
        print(f"\n테스트 실행 중 최상위 오류: {e}")
        traceback.print_exc()
