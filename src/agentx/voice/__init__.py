"""Voice I/O for AgentX — provider-agnostic Speech-to-Text and Text-to-Speech.

Both auto-detect their backend (local first, cloud fallback), mirroring the rest
of AgentX: works keyless/local out of the box, upgrades to cloud when keys exist.

    from agentx.voice import transcribe, synthesize

    text = transcribe("question.wav").text
    audio = synthesize("Here is the answer.").audio

Install backends with ``uv pip install 'agentx-kit[voice]'``.
"""
from .stt import STTResult, SpeechToText, available_stt_backends, transcribe
from .tts import TTSResult, TextToSpeech, available_tts_backends, synthesize

__all__ = [
    "transcribe",
    "STTResult",
    "SpeechToText",
    "available_stt_backends",
    "synthesize",
    "TTSResult",
    "TextToSpeech",
    "available_tts_backends",
]
