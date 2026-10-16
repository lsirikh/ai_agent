"""
gTTS 빠른 테스트 - 한국어 TTS
"""
import io
import sys
import time

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("gTTS 한국어 TTS 빠른 테스트")
print("=" * 50)

# gTTS 로드
print("\n1. gTTS 로드 중...")
from gtts import gTTS
import pygame

# 테스트 텍스트
test_text = "안녕하세요! 저는 엣지보이스 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
print(f"   텍스트: {test_text}")

# TTS 생성
print("\n2. TTS 생성 중...")
start = time.time()
tts = gTTS(text=test_text, lang='ko')
buffer = io.BytesIO()
tts.write_to_fp(buffer)
buffer.seek(0)
gen_time = time.time() - start
print(f"   생성 완료! ({gen_time:.2f}초, {len(buffer.getvalue())} bytes)")

# 재생
print("\n3. 재생 중...")
pygame.mixer.init()
pygame.mixer.music.load(buffer)
pygame.mixer.music.play()

while pygame.mixer.music.get_busy():
    time.sleep(0.1)

pygame.mixer.quit()
print("   ✅ 재생 완료!")

print("\n" + "=" * 50)
print("테스트 성공!")
