import sys
import threading
import queue
import time
import traceback

import torch

try:
    import whisper
    import sounddevice as sd
    import numpy as np
except ImportError as e:
    print(f"오류: STT 서비스에 필요한 라이브러리를 찾을 수 없습니다 ({e}).")
    print("다음 명령어를 실행하여 설치하세요:")
    print("uv add openai-whisper sounddevice numpy")
    raise

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
SILENCE_THRESHOLD = 500
SILENCE_DURATION = 1.5


class STTService:
    """
    Whisper를 이용한 음성-텍스트 변환 서비스 클래스
    """

    def __init__(self, model_name="base", device_preference="auto"):
        """
        서비스 초기화 및 Whisper 모델 로드
        Args:
            model_name (str): 사용할 Whisper 모델 이름 또는 경로
            device_preference (str): 사용할 장치 설정 ('auto', 'cpu', 'mps')
        """
        self.model_name = model_name
        self.device_preference = device_preference
        self.whisper_model = None
        self.audio_queue = queue.Queue()
        self.stop_recording_event = threading.Event()
        self._load_model()

    def _load_model(self):
        """Whisper 모델 로드 (사용자 설정 또는 자동 감지 기반)"""
        print(
            f"Whisper 모델 '{self.model_name}' 로드 중 (선호 장치: {self.device_preference})..."
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

        try:
            self.whisper_model = whisper.load_model(
                self.model_name, device=device, download_root="./models"
            )
            print(f"Whisper 모델 로드 완료 (사용 장치: {device}).")
        except Exception as e:
            print(f"Whisper 모델 로드 중 심각한 오류 발생: {e}")
            traceback.print_exc()
            raise RuntimeError(f"Whisper 모델 '{self.model_name}' 로드 실패") from e

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

    def transcribe_audio(self, audio_data):
        """
        Whisper 모델을 사용하여 오디오 데이터를 텍스트로 변환.
        이 함수는 동기적으로 실행되므로 별도 스레드에서 호출해야 합니다.
        """
        if self.whisper_model is None:
            print("오류: Whisper 모델이 로드되지 않았습니다.")
            return ""
        if audio_data is None or len(audio_data) == 0:
            print("변환할 오디오 데이터가 없습니다.")
            return ""

        print(f"Whisper로 음성 변환 중 (장치: {self.whisper_model.device})...")
        try:
            use_fp16 = self.whisper_model.device != "cpu"

            result = self.whisper_model.transcribe(audio_data, fp16=use_fp16)
            transcribed_text = result["text"].strip()
            print("음성 변환 완료.")
            return transcribed_text
        except Exception as e:
            print(f"Whisper 변환 중 오류 발생: {e}")
            traceback.print_exc()
            return ""

    def stop_recording(self):
        """외부에서 녹음을 중지시킬 때 호출"""
        print("녹음 중지 요청 수신.")
        self.stop_recording_event.set()


async def test_stt_service():
    """stt_service.py 단독 실행 시 테스트 함수"""
    print("STT 서비스 테스트 시작...")
    try:
        stt = STTService(model_name="base")

        print("\n--- 녹음 테스트 ---")
        audio = await asyncio.to_thread(stt.record_audio)

        if audio is not None:
            print(f"녹음된 오디오 데이터 길이: {len(audio)} 샘플")
            print("\n--- 변환 테스트 ---")
            text = await asyncio.to_thread(stt.transcribe_audio, audio)
            print(f"\n변환된 텍스트: '{text}'")
        else:
            print("녹음에 실패하여 변환 테스트를 건너뜁니다.")

    except RuntimeError as e:
        print(f"STT 서비스 초기화 실패: {e}")
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
