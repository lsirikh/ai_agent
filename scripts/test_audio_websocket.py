"""
테스트용 WebSocket 오디오 클라이언트

실제 WAV 파일을 사용하여 audio-gateway에 전송합니다.
"""
import asyncio
import numpy as np
import websockets
import json
import soundfile as sf
import sys


async def send_audio_file(file_path: str):
    """WAV 파일을 읽어서 WebSocket으로 전송"""
    uri = "ws://localhost:11008/ws/audio"

    print(f"Loading audio file: {file_path}")

    # 오디오 파일 로드
    audio, sample_rate = sf.read(file_path)

    # 스테레오 -> 모노
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)

    # 16kHz로 리샘플링 (간단한 방식)
    if sample_rate != 16000:
        ratio = 16000 / sample_rate
        new_length = int(len(audio) * ratio)
        indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
        audio = audio[indices]

    # float32로 변환
    audio = audio.astype(np.float32)

    print(f"Audio loaded: {len(audio)} samples ({len(audio)/16000:.2f}s)")
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Sending audio chunks...")

            chunk_size = 1600  # 100ms @ 16kHz
            num_chunks = len(audio) // chunk_size
            speech_detected = 0

            for i in range(num_chunks):
                start = i * chunk_size
                end = start + chunk_size
                chunk = audio[start:end]

                # 전송
                await ws.send(chunk.tobytes())

                # VAD 결과 수신
                response = await ws.recv()
                result = json.loads(response)

                is_speech = result.get('is_speech', False)
                prob = result.get('probability', 0)

                if is_speech:
                    speech_detected += 1

                if i % 10 == 0 or is_speech:
                    print(f"Chunk {i}/{num_chunks}: is_speech={is_speech}, prob={prob:.2f}")

                await asyncio.sleep(0.05)  # 50ms 간격 (빠르게 테스트)

            print(f"\nTest complete! Speech detected in {speech_detected}/{num_chunks} chunks")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # 기본 테스트 파일
    default_file = r"c:\source\python\AI agent\output\tts_output.wav"

    file_path = sys.argv[1] if len(sys.argv) > 1 else default_file
    asyncio.run(send_audio_file(file_path))