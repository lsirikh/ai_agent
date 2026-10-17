"""
vLLM 로짓 처리기: 한자·가나·전각 문장부호 토큰을 고를 수 없게 막는다
(중국어 출력 원천 차단).

    vllm serve … --logits-processors edgevoice_guard.han_guard:HanBlockLogitsProcessor
    (PYTHONPATH 에 이 패키지의 부모 폴더, EDGEVOICE_BLOCK_HAN=0 이면 끈다)

vLLM 0.31 Model Runner V2 인터페이스. 모든 요청에 적용된다(답·도구 인자 모두).
막는 토큰은 시작할 때 한 번 고른다. 이 모듈은 프런트엔드에서도 불려 오므로
torch 등 무거운 것은 처리기를 만들 때 가져온다.
"""

from __future__ import annotations

import logging
import os

from vllm.v1.worker.gpu.sample.logits_processor import LogitsProcessor

from .han_tokens import banned_token_ids

logger = logging.getLogger(__name__)


def _bytes_to_unicode() -> dict:
    """GPT-2 바이트 수준 BPE 의 바이트 → 문자 표(Qwen 도 같다)."""
    printable = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    chars = printable[:]
    extra = 0
    for byte in range(256):
        if byte not in printable:
            printable.append(byte)
            chars.append(256 + extra)
            extra += 1
    return dict(zip(printable, map(chr, chars)))


def _byte_reader(tokenizer):
    """바이트 수준 BPE 토큰(GPT-2 방식 문자열) → 원래 바이트. 특수 토큰은 None."""
    byte_of = {char: byte for byte, char in _bytes_to_unicode().items()}

    def raw(token_id: int):
        token = tokenizer.convert_ids_to_tokens(token_id)
        if not token or any(char not in byte_of for char in token):
            return None
        return bytes(byte_of[char] for char in token)

    return raw


class HanBlockLogitsProcessor(LogitsProcessor):
    def __init__(self, vllm_config, req_states) -> None:
        self.mask = None
        if os.getenv("EDGEVOICE_BLOCK_HAN", "1") == "0":
            logger.info("EdgeVoice 한자 차단 꺼짐 (EDGEVOICE_BLOCK_HAN=0)")
            return
        import torch
        from transformers import AutoTokenizer

        model = vllm_config.model_config
        tokenizer = AutoTokenizer.from_pretrained(
            model.tokenizer, trust_remote_code=model.trust_remote_code
        )
        vocab_size = req_states.vocab_size
        raw = _byte_reader(tokenizer)
        ids = [
            i
            for i in banned_token_ids(
                lambda i: tokenizer.decode([i]), len(tokenizer), raw_bytes=raw
            )
            if i < vocab_size
        ]
        mask = torch.zeros(vocab_size, dtype=torch.bool)
        mask[ids] = True
        self.mask = mask.to(req_states.device)
        logger.warning("EdgeVoice 한자 차단: %d / %d 토큰", len(ids), vocab_size)

    def add_request(self, req_idx: int, sampling_params) -> bool:
        return self.mask is not None

    def apply(self, logits, ctx):
        if self.mask is None:
            return logits
        width = min(logits.shape[-1], self.mask.shape[0])
        logits[:, :width].masked_fill_(self.mask[:width], float("-inf"))
        return logits
