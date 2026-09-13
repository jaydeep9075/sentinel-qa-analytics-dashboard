"""Push-to-talk voice for chat and chart.

The browser records a question and /voice/transcribe turns it into text. The
frontend then sends that text through the ordinary /chat or /chart pipeline,
so a spoken question is answered from exactly the same data as a typed one.
/voice/speak finally turns the answer into a short spoken reply.

This talks to Gemini through google-genai rather than litellm: neither audio
input nor speech output fits LLMClient's single-text-message shape. Usage is
still recorded through LLMClient's bookkeeping, so voice tokens count toward
the same per-user quota and Admin -> Usage totals as everything else.
"""

import io
import logging
import os
import re
import wave
from types import SimpleNamespace
from typing import Literal, Optional, Tuple

from google import genai
from google.genai import types

from . import app_settings, config, llm_client
from .prompts import VOICE_SUMMARY_PROMPT, VOICE_TRANSCRIBE_PROMPT

logger = logging.getLogger(__name__)

# Hears the question and writes the spoken summary. Flash-lite was the
# fastest of the models tried (~1.9 s for a one-sentence question) with an
# identical transcript, and both jobs are short, literal ones.
TEXT_MODEL = (os.getenv("VOICE_TEXT_MODEL") or "gemini-3.5-flash-lite").strip()
TTS_MODEL = (os.getenv("VOICE_TTS_MODEL") or "gemini-3.1-flash-tts-preview").strip()
TTS_VOICE = (os.getenv("VOICE_TTS_VOICE") or "Kore").strip()

# About 60 s of 16 kHz mono 16-bit WAV, which is what the browser sends.
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_SPEAK_CHARS = 6000
# A chat answer this short is already speakable; summarising it would only
# add a model round-trip in front of the speech.
_SUMMARY_WORD_THRESHOLD = 35
_DEFAULT_PCM_RATE = 24000
_REQUEST_TIMEOUT_MS = 30000
_NO_SPEECH = "NO_SPEECH"


class VoiceNotConfigured(Exception):
    """No Gemini key is available - the voice feature cannot run at all."""


class VoiceError(Exception):
    """A Gemini voice call failed or returned nothing usable."""


def _gemini_api_key() -> str:
    """The key the rest of the app already uses when Gemini is the active
    provider (which covers a key saved in Admin -> Settings); otherwise a
    Gemini key from the environment.

    Never falls back to LLM_API_KEY while another provider is active - that
    key belongs to that provider, and sending it to Google would only fail.
    """
    settings = app_settings.get_llm_settings(include_secret=True)
    provider = str(settings.get("provider") or "").strip().lower()
    if provider == "gemini" and settings.get("api_key"):
        return str(settings["api_key"])
    for name in config._provider_key_vars("gemini"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    raise VoiceNotConfigured(
        "Voice needs a Gemini API key. Set GEMINI_API_KEY in .env, "
        "or choose Gemini in Admin -> Settings."
    )


_client_cache: Optional[Tuple[str, genai.Client]] = None


def _client() -> genai.Client:
    # Rebuilt when the key changes, so an admin editing it in Settings takes
    # effect on the next request, the same as LLMClient.
    global _client_cache
    key = _gemini_api_key()
    if _client_cache is None or _client_cache[0] != key:
        _client_cache = (
            key,
            genai.Client(api_key=key, http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS)),
        )
    return _client_cache[1]


def _record_usage(response, model: str, user_id: str, workspace_id: str) -> None:
    meta = getattr(response, "usage_metadata", None)
    prompt_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
    completion_tokens = int(getattr(meta, "candidates_token_count", 0) or 0)
    total_tokens = int(getattr(meta, "total_token_count", 0) or 0) or prompt_tokens + completion_tokens
    usage = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    )
    llm_client.LLMClient()._record_usage(usage, f"gemini/{model}", user_id, workspace_id)


async def _generate(model: str, contents, gen_config, user_id: str, workspace_id: str):
    client = _client()
    try:
        response = await client.aio.models.generate_content(
            model=model, contents=contents, config=gen_config
        )
    except Exception as exc:
        logger.warning("Voice call to %s failed: %s", model, exc)
        raise VoiceError(f"The voice service could not be reached ({type(exc).__name__}).") from exc
    _record_usage(response, model, user_id, workspace_id)
    return response


def _text_config(temperature: float) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=temperature,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_MARKDOWN_RE = re.compile(r"[*_`#>|~]+")
_BULLET_RE = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)


def plain_speech(text: str) -> str:
    """Strip what a speech voice would read out literally or stumble on."""
    text = _LINK_RE.sub(r"\1", text or "")
    text = _EMOJI_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    return " ".join(text.split())


def _first_sentences(text: str, count: int = 2, max_chars: int = 300) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:count])[:max_chars].strip()


async def transcribe(audio: bytes, mime_type: str, user_id: str, workspace_id: str) -> str:
    """The spoken question as plain text, or "" when nothing intelligible was said."""
    response = await _generate(
        TEXT_MODEL,
        [VOICE_TRANSCRIBE_PROMPT, types.Part.from_bytes(data=audio, mime_type=mime_type)],
        _text_config(temperature=0),
        user_id,
        workspace_id,
    )
    text = " ".join((response.text or "").split()).strip("\"'“” ")
    if not text or text.upper().rstrip(".") == _NO_SPEECH:
        return ""
    return text


async def spoken_summary(answer: str, user_id: str, workspace_id: str) -> str:
    """A chat answer condensed to one or two sentences meant to be heard."""
    response = await _generate(
        TEXT_MODEL,
        VOICE_SUMMARY_PROMPT.format(answer=answer[:MAX_SPEAK_CHARS]),
        _text_config(temperature=0.2),
        user_id,
        workspace_id,
    )
    summary = plain_speech(response.text or "")
    return summary or _first_sentences(plain_speech(answer))


def pcm_rate(mime_type: Optional[str]) -> int:
    # Seen in practice: "audio/L16;codec=pcm;rate=24000" and
    # "audio/l16; rate=24000; channels=1" - the models disagree on format.
    match = re.search(r"rate=(\d+)", mime_type or "", re.IGNORECASE)
    return int(match.group(1)) if match else _DEFAULT_PCM_RATE


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM (what Gemini TTS returns) so a browser can play it."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


async def synthesize(text: str, user_id: str, workspace_id: str) -> bytes:
    """`text` read aloud, as WAV bytes."""
    response = await _generate(
        TTS_MODEL,
        text,
        types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
        user_id,
        workspace_id,
    )
    for candidate in response.candidates or []:
        for part in getattr(candidate.content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            if blob and blob.data:
                return pcm_to_wav(blob.data, pcm_rate(blob.mime_type))
    raise VoiceError("The voice service returned no audio.")


async def speak(
    text: str,
    kind: Literal["chat", "chart"],
    user_id: str,
    workspace_id: str,
) -> Tuple[str, bytes]:
    """(what is said, WAV bytes) for an answer.

    A chart's insight line is already a single sentence computed from the
    drawn data, so it is spoken as-is; a chat answer is summarised first
    unless it is already short enough to hear in full.
    """
    spoken = plain_speech(text)
    if kind == "chat" and len(spoken.split()) > _SUMMARY_WORD_THRESHOLD:
        spoken = await spoken_summary(text, user_id, workspace_id)
    if not spoken:
        raise VoiceError("There is nothing to say for this answer.")
    audio = await synthesize(spoken, user_id, workspace_id)
    return spoken, audio
