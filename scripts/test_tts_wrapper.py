"""
TTS Wrapper 모듈 테스트

services.tts 모듈의 MeloTTS 래퍼를 테스트
"""
import os
import sys
import time

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.tts import synthesize, is_available, init_melo_tts


def main():
    print("=" * 60)
    print("TTS Wrapper 모듈 테스트")
    print("=" * 60)

    # 1. 사용 가능 여부 확인
    print("\n1. MeloTTS 사용 가능 여부 확인...")
    if is_available():
        print("   ✅ MeloTTS 사용 가능")
    else:
        print("   ❌ MeloTTS 사용 불가 - 필요한 패키지 설치 필요")
        return

    # 2. TTS 초기화
    print("\n2. MeloTTS 초기화...")
    start = time.time()
    tts, speaker_id = init_melo_tts()
    init_time = time.time() - start
    print(f"   초기화 완료 ({init_time:.2f}초)")

    # 3. 음성 합성
    print("\n3. 음성 합성 테스트...")
    test_text = "안녕하세요! 저는 엣지보이스 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
    print(f"   텍스트: {test_text}")

    start = time.time()
    output_path = synthesize(test_text)
    synth_time = time.time() - start
    print(f"   ✅ 합성 완료 ({synth_time:.2f}초)")
    print(f"   출력 파일: {output_path}")

    # 4. 재생
    print("\n4. 음성 재생...")
    try:
        import pygame

        pygame.mixer.init()
        pygame.mixer.music.load(output_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.quit()
        print("   ✅ 재생 완료!")
    except Exception as e:
        print(f"   재생 실패: {e}")
        print(f"   수동으로 파일을 재생하세요: {output_path}")

    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
