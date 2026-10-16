"""
MeloTTS 한국어 TTS 테스트 - mecab-python3 패치 적용

Windows에서 eunjeon 대신 mecab-python3 사용
"""
import os
import sys
import time

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("MeloTTS 한국어 TTS 테스트 (mecab-python3 패치)")
print("=" * 60)

# mecab-python3로 eunjeon 대체하는 패치
print("\n1. mecab-python3 패치 적용 중...")

# MeCab wrapper 클래스 생성
class MeCabWrapper:
    """eunjeon.Mecab() 호환 래퍼"""
    def __init__(self):
        import MeCab
        # unidic 사전 경로 설정
        import unidic
        dicdir = unidic.DICDIR
        self.tagger = MeCab.Tagger(f'-d "{dicdir}"')

    def pos(self, text):
        """형태소 분석 결과를 (형태소, 품사) 튜플 리스트로 반환"""
        self.tagger.parse('')  # 버퍼 초기화
        node = self.tagger.parseToNode(text)
        result = []
        while node:
            if node.surface:
                features = node.feature.split(',')
                pos = features[0] if features else 'UNK'
                result.append((node.surface, pos))
            node = node.next
        return result

# g2pkk.G2p 클래스 패치
import g2pkk.g2pkk as g2pkk_module

# 원래 get_mecab 메서드 백업
original_get_mecab = g2pkk_module.G2p.get_mecab
original_check_mecab = g2pkk_module.G2p.check_mecab

def patched_check_mecab(self):
    """mecab 체크 건너뛰기"""
    pass

def patched_get_mecab(self):
    """mecab-python3 + unidic 사용"""
    return MeCabWrapper()

# 패치 적용
g2pkk_module.G2p.check_mecab = patched_check_mecab
g2pkk_module.G2p.get_mecab = patched_get_mecab

print("   ✅ 패치 완료!")

# MeloTTS 로드
print("\n2. MeloTTS 로드 중...")
from melo.api import TTS

# CUDA 확인
import torch
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"   Device: {device}")

# TTS 모델 로드
print("\n3. TTS 모델 로드...")
tts = TTS(language='KR', device=device)
print("   ✅ 모델 로드 완료!")

# 스피커 ID 가져오기
speaker_ids = tts.hps.data.spk2id
print(f"   사용 가능한 스피커: {list(speaker_ids.keys())}")

# 첫 번째 스피커 사용
speaker_id = speaker_ids['KR']
print(f"   선택된 스피커: KR (ID: {speaker_id})")

# 출력 디렉토리 생성
output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'melo_kr_result.wav')

# TTS 생성
print("\n4. TTS 생성 중...")
test_text = "안녕하세요! 저는 엣지보이스 AI 어시스턴트입니다."
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
    print(f"수동 재생: {output_path}")

print("\n" + "=" * 60)
