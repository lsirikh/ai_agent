"""
마이크 → STT → LLM → TTS → 스피커 전체 파이프라인 테스트

마이크에서 녹음 → STT 변환 → LLM 응답 생성 → TTS 합성 → 스피커 재생
"""
import io
import os
import sys
import time
import wave
from datetime import datetime

import numpy as np
import requests
import sounddevice as sd
import pygame

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 설정
RATE = 16000  # STT용 샘플레이트
RECORD_SECONDS = 10

STT_URL = "http://localhost:11001/transcribe"
LLM_URL = "http://localhost:11003/v1/chat/completions"

# TTS 설정: "melo" (MeloTTS 한국어) 또는 "gtts" (Google TTS)
TTS_MODE = "melo"

# MeloTTS 전역 변수 (한 번만 로드)
_melo_tts = None
_melo_speaker_id = None
_melo_output_path = None


def init_melo_tts():
    """MeloTTS 초기화 (mecab-python3 패치 적용)"""
    global _melo_tts, _melo_speaker_id, _melo_output_path

    if _melo_tts is not None:
        return _melo_tts, _melo_speaker_id

    print("🔧 MeloTTS 초기화 중...")

    # mecab-python3로 eunjeon 대체하는 패치
    class MeCabWrapper:
        def __init__(self):
            import MeCab
            import unidic
            self.tagger = MeCab.Tagger(f'-d "{unidic.DICDIR}"')

        def pos(self, text):
            self.tagger.parse('')
            node = self.tagger.parseToNode(text)
            result = []
            while node:
                if node.surface:
                    features = node.feature.split(',')
                    pos = features[0] if features else 'UNK'
                    result.append((node.surface, pos))
                node = node.next
            return result

    import g2pkk.g2pkk as g2pkk_module
    g2pkk_module.G2p.check_mecab = lambda self: None
    g2pkk_module.G2p.get_mecab = lambda self: MeCabWrapper()

    # MeloTTS 로드
    from melo.api import TTS
    import torch

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    _melo_tts = TTS(language='KR', device=device)
    _melo_speaker_id = _melo_tts.hps.data.spk2id['KR']

    # 출력 경로 설정
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    os.makedirs(output_dir, exist_ok=True)
    _melo_output_path = os.path.join(output_dir, 'tts_output.wav')

    print(f"✅ MeloTTS 로드 완료 (device: {device})")
    return _melo_tts, _melo_speaker_id


def record_audio(duration: int = RECORD_SECONDS) -> bytes:
    """마이크에서 오디오 녹음"""
    print(f"\n🎤 {duration}초간 마이크 녹음을 시작합니다...")
    print("   말씀해 주세요!")

    # sounddevice로 녹음
    audio_data = sd.rec(
        int(duration * RATE),
        samplerate=RATE,
        channels=1,
        dtype=np.int16
    )

    # 남은 시간 표시
    for i in range(duration, 0, -1):
        print(f"   녹음 중... {i}초 남음")
        sd.sleep(1000)  # 1초 대기

    sd.wait()  # 녹음 완료까지 대기
    print("✅ 녹음 완료!")

    # WAV 형식으로 변환
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(RATE)
        wf.writeframes(audio_data.tobytes())

    return buffer.getvalue()


def transcribe_audio(audio_data: bytes, language: str = "ko") -> str:
    """STT: 오디오를 텍스트로 변환"""
    print("\n🔄 STT 변환 중...")

    files = {'audio': ('audio.wav', audio_data, 'audio/wav')}
    data = {'language': language}  # 한국어 명시
    response = requests.post(STT_URL, files=files, data=data, timeout=30)

    if response.status_code == 200:
        result = response.json()
        text = result.get('text', '')
        confidence = result.get('confidence', 0)
        print(f"✅ STT 완료: '{text}' (신뢰도: {confidence:.2f})")
        return text
    else:
        print(f"❌ STT 실패: {response.status_code}")
        return ""


def generate_response(user_input: str) -> str:
    """LLM: 응답 생성"""
    print("\n🤖 LLM 응답 생성 중...")

    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "messages": [
            {
                "role": "system",
                "content": "당신은 친절한 AI 어시스턴트입니다. 특정 단어 외에는 반드시 한국어 외에 다른언어를 사용하지 않는다."
            },
            {
                "role": "user",
                "content": user_input
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.8
    }

    response = requests.post(LLM_URL, json=payload, timeout=60)

    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content']
        print(f"✅ LLM 응답: '{content}'")
        return content
    else:
        print(f"❌ LLM 실패: {response.status_code}")
        return ""


def synthesize_speech_melo(text: str) -> str:
    """TTS: MeloTTS로 음성 합성 (파일 경로 반환)"""
    global _melo_output_path

    tts, speaker_id = init_melo_tts()
    tts.tts_to_file(text, speaker_id, _melo_output_path, speed=1.0)
    return _melo_output_path


def synthesize_speech_gtts(text: str) -> bytes:
    """TTS: gTTS로 음성 합성 (바이트 반환)"""
    from gtts import gTTS

    tts = gTTS(text=text, lang='ko')
    buffer = io.BytesIO()
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def synthesize_speech(text: str):
    """TTS: 텍스트를 음성으로 변환"""
    print("\n🔊 TTS 합성 중...")

    try:
        if TTS_MODE == "melo":
            result = synthesize_speech_melo(text)
            print(f"✅ TTS 완료 (MeloTTS): {result}")
        else:
            result = synthesize_speech_gtts(text)
            print(f"✅ TTS 완료 (gTTS): {len(result)} bytes")
        return result
    except Exception as e:
        print(f"❌ TTS 실패: {e}")
        return None


def play_audio(audio_data):
    """스피커로 오디오 재생"""
    print("\n🔈 스피커 재생 중...")

    try:
        pygame.mixer.init()

        if TTS_MODE == "melo":
            # WAV 파일 경로
            pygame.mixer.music.load(audio_data)
        else:
            # MP3 바이트 데이터
            buffer = io.BytesIO(audio_data)
            pygame.mixer.music.load(buffer)

        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.quit()
        print("✅ 재생 완료!")

    except Exception as e:
        print(f"❌ 재생 실패: {e}")
        try:
            pygame.mixer.quit()
        except:
            pass


def test_stt_only():
    """STT만 테스트"""
    print("\n" + "="*60)
    print("STT 단독 테스트")
    print("="*60)

    audio_data = record_audio(RECORD_SECONDS)
    text = transcribe_audio(audio_data)

    if text:
        print(f"\n📝 인식된 텍스트: '{text}'")
    else:
        print("\n⚠️ 텍스트 인식 실패")


def test_tts_only():
    """TTS만 테스트"""
    print("\n" + "="*60)
    print(f"TTS 단독 테스트 (Mode: {TTS_MODE})")
    print("="*60)

    test_text = "안녕하세요! 저는 엣지보이스 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
    print(f"테스트 텍스트: '{test_text}'")

    audio_data = synthesize_speech(test_text)

    if audio_data:
        play_audio(audio_data)


def test_full_pipeline():
    """전체 파이프라인 테스트"""
    print("\n" + "="*60)
    print("전체 파이프라인 테스트: 마이크 → STT → LLM → TTS → 스피커")
    print("="*60)

    start_time = datetime.now()

    # 1. 마이크 녹음
    audio_data = record_audio(RECORD_SECONDS)
    record_time = (datetime.now() - start_time).total_seconds()

    # 2. STT 변환
    stt_start = datetime.now()
    user_text = transcribe_audio(audio_data)
    stt_time = (datetime.now() - stt_start).total_seconds()

    if not user_text or user_text.strip() == "":
        print("\n⚠️ 음성이 인식되지 않았습니다. 더 크게 말씀해 주세요.")
        return

    # 3. LLM 응답 생성
    llm_start = datetime.now()
    response_text = generate_response(user_text)
    llm_time = (datetime.now() - llm_start).total_seconds()

    if not response_text:
        print("\n⚠️ LLM 응답 생성 실패")
        return

    # 4. TTS 합성
    tts_start = datetime.now()
    audio_response = synthesize_speech(response_text)
    tts_time = (datetime.now() - tts_start).total_seconds()

    if not audio_response:
        print("\n⚠️ TTS 합성 실패")
        return

    # 5. 스피커 재생
    play_audio(audio_response)

    total_time = (datetime.now() - start_time).total_seconds() - record_time

    # 결과 요약
    print("\n" + "="*60)
    print("📊 파이프라인 결과 요약")
    print("="*60)
    print(f"👤 사용자 입력: '{user_text}'")
    print(f"🤖 AI 응답: '{response_text}'")
    print("-"*60)
    print("⏱️ 처리 시간:")
    print(f"   STT: {stt_time:.2f}초")
    print(f"   LLM: {llm_time:.2f}초")
    print(f"   TTS: {tts_time:.2f}초")
    print(f"   총합: {total_time:.2f}초 (녹음 제외)")


def main():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           EdgeVoice 마이크/스피커 테스트                        ║
║           TTS Mode: {TTS_MODE.upper():^10}                   ║
╚══════════════════════════════════════════════════════════════╝

테스트 옵션:
  1. STT 단독 테스트 (마이크 → 텍스트)
  2. TTS 단독 테스트 (텍스트 → 스피커)
  3. 전체 파이프라인 테스트 (마이크 → STT → LLM → TTS → 스피커)
  q. 종료
""")

    while True:
        choice = input("\n선택 (1/2/3/q): ").strip()

        if choice == '1':
            test_stt_only()
        elif choice == '2':
            test_tts_only()
        elif choice == '3':
            test_full_pipeline()
        elif choice.lower() == 'q':
            print("\n종료합니다.")
            break
        else:
            print("잘못된 선택입니다.")


if __name__ == "__main__":
    main()
