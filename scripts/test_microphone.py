"""
마이크 입력을 WebSocket으로 전송하는 테스트 클라이언트

실시간으로 마이크 오디오를 audio-gateway에 전송하고 VAD 결과를 표시합니다.
"""
import asyncio
import numpy as np
import websockets
import json

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("sounddevice 설치 필요: pip install sounddevice")


SAMPLE_RATE = 16000
CHUNK_SIZE = 1600  # 100ms @ 16kHz


async def microphone_stream():
    """마이크 입력을 WebSocket으로 전송"""
    if not SOUNDDEVICE_AVAILABLE:
        print("sounddevice가 설치되지 않았습니다.")
        return

    uri = "ws://localhost:11008/ws/audio"
    print(f"Connecting to {uri}...")
    print("마이크에 말씀해주세요. Ctrl+C로 종료합니다.\n")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected! 마이크 스트리밍 시작...\n")

            # 오디오 버퍼
            audio_queue = asyncio.Queue()

            def audio_callback(indata, frames, time_info, status):
                """sounddevice 콜백 - 오디오 데이터를 큐에 추가"""
                if status:
                    print(f"Audio status: {status}")
                # float32로 변환
                audio_queue.put_nowait(indata.copy().flatten().astype(np.float32))

            # 마이크 스트림 시작
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                blocksize=CHUNK_SIZE,
                callback=audio_callback
            ):
                chunk_count = 0
                speech_count = 0

                while True:
                    # 오디오 청크 가져오기
                    audio_chunk = await audio_queue.get()

                    # WebSocket으로 전송
                    await ws.send(audio_chunk.tobytes())

                    # VAD 결과 수신
                    response = await ws.recv()
                    result = json.loads(response)

                    is_speech = result.get('is_speech', False)
                    prob = result.get('probability', 0)

                    chunk_count += 1
                    if is_speech:
                        speech_count += 1

                    # 음성 감지 시 또는 5초마다 출력
                    if is_speech or chunk_count % 50 == 0:
                        status = "🎤 음성 감지!" if is_speech else "..."
                        print(f"[{chunk_count:4d}] prob={prob:.2f} {status}")

    except KeyboardInterrupt:
        print(f"\n\n종료! 총 {chunk_count} 청크, 음성 {speech_count}회 감지")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(microphone_stream())