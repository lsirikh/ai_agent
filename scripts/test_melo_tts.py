"""
MeloTTS 한국어 TTS 테스트 스크립트

OpenVoice 음성변환 없이 MeloTTS 기본 음성만 사용
"""
import os
import sys
import time

# 경로 설정 - MeloTTS 패키지는 pip으로 설치됨
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'models', 'realtime_tts_ko'))

def main():
    print("=" * 60)
    print("MeloTTS 한국어 TTS 테스트")
    print("=" * 60)

    # MeloTTS 로드
    print("\n1. MeloTTS 로드 중...")
    from melo.api import TTS

    # CUDA 확인
    import torch
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"   Device: {device}")

    # TTS 모델 로드
    print("\n2. TTS 모델 로드...")
    tts = TTS(language='KR', device=device)
    print("   모델 로드 완료!")

    # 스피커 ID 가져오기
    speaker_ids = tts.hps.data.spk2id
    print(f"   사용 가능한 스피커: {list(speaker_ids.keys())}")

    # 첫 번째 스피커 사용
    for speaker_name, speaker_id in speaker_ids.items():
        print(f"   선택된 스피커: {speaker_name} (ID: {speaker_id})")
        break

    # 출력 디렉토리 생성
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'models', 'realtime_tts_ko', 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'melo_result.wav')

    # TTS 생성
    print("\n3. TTS 생성 중...")
    test_text = "안녕하세요. 저는 엣지보이스 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
    print(f"   텍스트: {test_text}")

    start_time = time.time()
    tts.tts_to_file(test_text, speaker_id, output_path, speed=1.0)
    gen_time = time.time() - start_time

    print(f"\n✅ TTS 생성 완료!")
    print(f"   출력 파일: {output_path}")
    print(f"   생성 시간: {gen_time:.2f}초")

    # 재생 (pygame 사용)
    try:
        import pygame

        print("\n🔈 재생 중...")
        pygame.mixer.init()
        pygame.mixer.music.load(output_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.quit()
        print("✅ 재생 완료!")
    except Exception as e:
        print(f"재생 실패: {e}")
        print(f"수동 재생 필요: {output_path}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
