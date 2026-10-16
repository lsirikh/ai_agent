"""
RealTime Zero-shot TTS 테스트 스크립트

OpenVoice + MeloTTS 기반 한국어 TTS 테스트
"""
import os
import sys

# 경로 설정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'models', 'realtime_tts_ko'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'models', 'realtime_tts_ko'))

from custom_tts import Custom_TTS

def main():
    print("=" * 60)
    print("RealTime Zero-shot TTS 테스트")
    print("=" * 60)

    # TTS 모듈 초기화
    print("\n1. TTS 모듈 초기화...")
    tts = Custom_TTS()

    # 모델 로드
    print("\n2. 모델 로드 중...")
    tts.set_model(language='KR')

    # 참조 화자 설정 (샘플 음성 사용)
    print("\n3. 참조 화자 설정...")
    tts.get_reference_speaker('sample_sunhi.mp3', vad=False)

    # TTS 생성
    print("\n4. TTS 생성 중...")
    test_text = "안녕하세요. 저는 엣지보이스 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
    print(f"   텍스트: {test_text}")
    tts.make_speech(test_text)

    print("\n" + "=" * 60)
    print("✅ TTS 생성 완료!")
    print(f"   출력 파일: output/result_0.wav")
    print("=" * 60)

    # 재생 (pygame 사용)
    try:
        import pygame
        import time

        print("\n🔈 재생 중...")
        pygame.mixer.init()
        pygame.mixer.music.load('output/result_0.wav')
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.quit()
        print("✅ 재생 완료!")
    except Exception as e:
        print(f"재생 실패: {e}")


if __name__ == "__main__":
    main()
