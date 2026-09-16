"""Push-to-talk voice for chat and chart.

The browser records a question; /voice/transcribe turns it into text plus the
language it was spoken in. The frontend then sends that text through the
ordinary /chat or /chart pipeline, so a spoken question is answered from
exactly the same data as a typed one. /voice/speak finally turns the answer
into a short spoken reply, in that same language.

This talks to Gemini through google-genai rather than litellm: neither audio
input nor speech output fits LLMClient's single-text-message shape. Usage is
still recorded through LLMClient's bookkeeping, so voice tokens count toward
the same per-user quota and Admin -> Usage totals as everything else.

Latency matters more here than anywhere else in the app, because a spoken
turn is several network round-trips deep (transcribe -> chat -> condense ->
speak) and every one of them is heard as a pause. So:
  * Thinking is switched off on the two text calls. Transcribing and
    condensing are literal jobs; a flash model otherwise spends a second or
    more deliberating over them, for no gain in accuracy.
  * Output length is capped, so the model stops rather than padding.
  * Identical spoken text is served from an in-process cache, which makes
    replaying an answer - or re-hearing a chart insight - instant and free.
  * The condensing call is skipped outright when the answer is already short
    enough to hear in full.
"""

import asyncio
import io
import json
import logging
import os
import re
import wave
from collections import OrderedDict
from types import SimpleNamespace
from typing import Dict, Literal, NamedTuple, Optional, Sequence, Set, Tuple

import litellm
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from . import app_settings, config, llm_client
from .prompts import VOICE_SUMMARY_PROMPT, VOICE_TRANSCRIBE_PROMPT

logger = logging.getLogger(__name__)


def _models(env_var: str, *defaults: str) -> Tuple[str, ...]:
    """Candidate model ids for one job, best first.

    An operator's VOICE_* override is tried first and the built-in defaults
    stay behind it as a safety net. A model id that has been retired, renamed,
    or that this deployment's key has no access to then costs one failed call
    once - after which the working one is remembered - instead of taking the
    whole voice feature down, which is what a single hard-coded id does.
    """
    override = (os.getenv(env_var) or "").strip()
    ordered = [override, *defaults] if override else list(defaults)
    return tuple(dict.fromkeys(name for name in ordered if name))


# Writes the spoken reply. Flash-lite was the fastest of the models tried
# (~1.9 s for a one-sentence question) and condensing an answer is a short,
# literal job that a small model does as well as a large one.
TEXT_MODELS = _models(
    "VOICE_TEXT_MODEL",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)
# Hearing the question is a separate list because it is a separate capability.
# Accepting text says nothing about accepting audio: gemini-3.5-flash-lite
# answers text happily and rejects an audio part with a bare 400, and the
# purpose-named gemini-3.5-transcribe refuses the JSON schema the transcript
# comes back in. Sharing one list also made the fallback search unwinnable,
# because whichever model the last summary settled on was tried first for the
# next question's audio.
TRANSCRIBE_MODELS = _models(
    "VOICE_TRANSCRIBE_MODEL",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)
# Every Gemini TTS id is preview-tier, so this chain is the one most likely to
# need it: preview names get retired or gated per key with no warning.
TTS_MODELS = _models(
    "VOICE_TTS_MODEL",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
)
TTS_VOICE = (os.getenv("VOICE_TTS_VOICE") or "Kore").strip()

# ── which service does the speech ───────────────────────────────────────────
#
# Speech is its OWN provider axis, deliberately separate from the chat LLM.
# "Use whatever the chat uses" cannot work as a rule: Anthropic ships no
# transcription or text-to-speech API at all, and neither does a local Ollama,
# so a Claude-only deployment has nothing to call. The mic therefore picks its
# own vendor, and when there is none the browser does the speech itself - which
# is why voice keeps working whatever LLM_PROVIDER is set to.
#
#   auto     pick a vendor from whatever keys exist (default)
#   gemini   force Gemini - native audio in, native speech out
#   openai   force OpenAI-compatible speech through litellm
#   browser  never call a vendor; the browser's own speech engine does it
SPEECH_PROVIDER = (os.getenv("VOICE_PROVIDER") or "auto").strip().lower()

# The litellm path, used for every vendor that isn't Gemini. whisper-1 leads
# because its verbose_json reports the language it heard, which the newer
# transcribe models don't.
STT_MODELS = _models("VOICE_STT_MODEL", "whisper-1", "gpt-4o-mini-transcribe")
LITELLM_TTS_MODELS = _models("VOICE_OPENAI_TTS_MODEL", "gpt-4o-mini-tts", "tts-1")
LITELLM_TTS_VOICE = (os.getenv("VOICE_OPENAI_TTS_VOICE") or "alloy").strip()

# Vendors this module can actually drive, best first. Anthropic is absent on
# purpose - there is no endpoint to call, not merely no integration written.
_SPEECH_VENDORS = ("gemini", "openai")

# About 60 s of 16 kHz mono 16-bit WAV, which is what the browser sends.
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_SPEAK_CHARS = 6000
# A chat answer this short is already speakable; condensing it would only add
# a model round-trip in front of the speech. Scripts written without spaces
# (Japanese, Chinese, Thai) make a word count meaningless, so length decides
# for those.
_SUMMARY_WORD_THRESHOLD = 35
_SUMMARY_CHAR_THRESHOLD = 240
_DEFAULT_PCM_RATE = 24000
# Split per job: transcribing and condensing are sub-second when healthy, so a
# long ceiling there only holds a stuck request open. Speech genuinely takes
# longer for a couple of sentences.
_TEXT_TIMEOUT_MS = 15000
_TTS_TIMEOUT_MS = 30000
_TRANSCRIBE_MAX_TOKENS = 512
_SUMMARY_MAX_TOKENS = 256
_RETRY_DELAY_SECONDS = 0.4
# Charged against the key rather than a model, so it is the one client error
# that must not send the fallback search down the rest of the list.
_RATE_LIMIT_STATUS = 429
_NO_SPEECH = "NO_SPEECH"


class VoiceNotConfigured(Exception):
    """No speech vendor is reachable, so the server cannot do the speech.

    Not fatal to the feature: the browser is told to use its own speech
    engine instead. See capabilities().
    """


class VoiceError(Exception):
    """A Gemini voice call failed or returned nothing usable."""


class Transcript(NamedTuple):
    """What was said, and the language it was said in.

    `language` is a BCP-47 tag Gemini's speech models accept, or "" when the
    language could not be pinned down - in which case everything downstream
    simply infers it from the words themselves.
    """

    text: str
    language: str


def _vendor_key(vendor: str) -> str:
    """`vendor`'s API key, or "" when this deployment has none.

    The key saved in Admin -> Settings only counts when it belongs to this
    vendor. Handing an Anthropic key to Google or OpenAI would surface as a
    401 from a vendor the user never chose, with nothing in the config
    looking wrong - the single most confusing failure this can have.
    """
    settings = app_settings.get_llm_settings(include_secret=True)
    if str(settings.get("provider") or "").strip().lower() == vendor and settings.get("api_key"):
        return str(settings["api_key"])
    for name in config._provider_key_vars(vendor):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def speech_vendor() -> str:
    """Which vendor should do the speech, or "" to leave it to the browser."""
    if SPEECH_PROVIDER == "browser":
        return ""
    if SPEECH_PROVIDER in _SPEECH_VENDORS:
        return SPEECH_PROVIDER if _vendor_key(SPEECH_PROVIDER) else ""
    # auto: prefer whichever vendor is already powering chat, so that one key
    # covers both and switching provider switches the voice with it.
    active = str(app_settings.get_llm_settings().get("provider") or "").strip().lower()
    for vendor in (active, *_SPEECH_VENDORS):
        if vendor in _SPEECH_VENDORS and _vendor_key(vendor):
            return vendor
    return ""


def capabilities() -> Dict[str, Optional[str]]:
    """What the browser needs to know before it wires up the mic."""
    vendor = speech_vendor()
    return {"mode": "server" if vendor else "browser", "provider": vendor or None}


def _gemini_api_key() -> str:
    key = _vendor_key("gemini")
    if not key:
        raise VoiceNotConfigured(
            "Voice needs a Gemini API key. Set GEMINI_API_KEY in .env, "
            "or choose Gemini in Admin -> Settings."
        )
    return key


_client_cache: Optional[Tuple[str, genai.Client]] = None


def _client() -> genai.Client:
    # Rebuilt when the key changes, so an admin editing it in Settings takes
    # effect on the next request, the same as LLMClient. Reusing the client
    # also reuses its connection pool, which is worth ~100 ms of TLS setup on
    # every call after the first. Timeouts are set per call instead, since
    # speech needs a longer one than transcription.
    global _client_cache
    key = _gemini_api_key()
    if _client_cache is None or _client_cache[0] != key:
        _client_cache = (key, genai.Client(api_key=key))
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


# ── calling Gemini ──────────────────────────────────────────────────────────

# The model from each candidate list that last worked, so the fallback search
# is paid for once per process rather than on every request.
_resolved_model: Dict[Tuple[str, ...], str] = {}
# Models that reject an explicit thinking budget (the Pro tiers require a
# non-zero one). Learned once, then honoured without a wasted call.
_rejects_thinking: Set[str] = set()


def _status_code(exc: Exception) -> Optional[int]:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _is_model_specific(exc: Optional[Exception]) -> bool:
    """True when the failure belongs to this model id, so the next candidate is
    worth a try.

    Every client error qualifies except a rate limit. A retired id answers 404,
    but a preview model that refuses a config its siblings accept answers a
    bare 400 INVALID_ARGUMENT with nothing in it naming the model - which is
    how the TTS chain used to die on its first candidate while two working
    ones sat behind it. A 429, by contrast, is spent against the key rather
    than the model, so walking the list would only burn the quota again.
    """
    if not isinstance(exc, genai_errors.ClientError):
        return False
    return _status_code(exc) != _RATE_LIMIT_STATUS


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (genai_errors.ServerError, asyncio.TimeoutError, TimeoutError)):
        return True
    code = _status_code(exc)
    return isinstance(code, int) and code >= 500


def _mentions_thinking(exc: Exception) -> bool:
    if not isinstance(exc, genai_errors.ClientError):
        return False
    message = str(exc).lower()
    return "thinking" in message or "thought" in message


def _without_thinking(gen_config: types.GenerateContentConfig) -> types.GenerateContentConfig:
    return gen_config.model_copy(update={"thinking_config": None})


async def _call_once(model: str, contents, gen_config: types.GenerateContentConfig):
    client = _client()
    effective = _without_thinking(gen_config) if model in _rejects_thinking else gen_config
    try:
        return await client.aio.models.generate_content(
            model=model, contents=contents, config=effective
        )
    except Exception as exc:
        if effective.thinking_config is None or not _mentions_thinking(exc):
            raise
        # This model insists on thinking. Note that and ask again the slow way,
        # rather than failing a user's question over a latency optimisation.
        logger.info("Model %s rejects an explicit thinking budget; retrying without it", model)
        _rejects_thinking.add(model)
        return await client.aio.models.generate_content(
            model=model, contents=contents, config=_without_thinking(gen_config)
        )


def _candidate_order(models: Tuple[str, ...]) -> Sequence[str]:
    preferred = _resolved_model.get(models)
    if not preferred:
        return models
    return (preferred, *(name for name in models if name != preferred))


async def _generate(
    models: Tuple[str, ...],
    contents,
    gen_config: types.GenerateContentConfig,
    user_id: str,
    workspace_id: str,
):
    last: Optional[Exception] = None
    for model in _candidate_order(models):
        for attempt in (1, 2):
            try:
                response = await _call_once(model, contents, gen_config)
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                last = exc
                if attempt == 1 and _is_transient(exc):
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                break
            _resolved_model[models] = model
            _record_usage(response, model, user_id, workspace_id)
            return response
        if not _is_model_specific(last):
            break
        logger.warning("Voice model %s is unavailable, falling back: %s", model, last)
        # A remembered model that has since started failing must not keep the
        # rest of the list behind it on the next request.
        _resolved_model.pop(models, None)

    logger.warning("Voice call failed for %s: %s", "/".join(models), last)
    raise VoiceError(f"The voice service could not be reached ({type(last).__name__}).") from last


def _text_config(temperature: float, max_output_tokens: int, **extra) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        # Transcribing and condensing are literal jobs. Left on, a flash
        # model's private reasoning pass adds a second or more to every spoken
        # turn and changes neither the transcript nor the summary.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=_TEXT_TIMEOUT_MS),
        **extra,
    )


# ── language ────────────────────────────────────────────────────────────────

# The languages Gemini's speech models take an explicit language_code for.
# Anything outside this set is left for the model to infer from the text,
# which it does well; sending an unsupported code is a hard API error, so this
# is a filter on the hint, not a limit on what can be spoken.
_TTS_LANGUAGES = frozenset({
    "ar-EG", "bn-BD", "de-DE", "en-IN", "en-US", "es-US", "fr-FR", "hi-IN",
    "id-ID", "it-IT", "ja-JP", "ko-KR", "mr-IN", "nl-NL", "pl-PL", "pt-BR",
    "ro-RO", "ru-RU", "ta-IN", "te-IN", "th-TH", "tr-TR", "uk-UA", "vi-VN",
})
# A bare "hi" is not a tag the API accepts, so each language gets the region
# its voices are actually trained on.
_DEFAULT_REGION = {
    "ar": "ar-EG", "bn": "bn-BD", "de": "de-DE", "en": "en-US", "es": "es-US",
    "fr": "fr-FR", "hi": "hi-IN", "id": "id-ID", "it": "it-IT", "ja": "ja-JP",
    "ko": "ko-KR", "mr": "mr-IN", "nl": "nl-NL", "pl": "pl-PL", "pt": "pt-BR",
    "ro": "ro-RO", "ru": "ru-RU", "ta": "ta-IN", "te": "te-IN", "th": "th-TH",
    "tr": "tr-TR", "uk": "uk-UA", "vi": "vi-VN",
}
MAX_LANGUAGE_CHARS = 16


def speech_language(code: Optional[str]) -> str:
    """`code` as a language tag Gemini TTS accepts, or "" to let it decide."""
    tag = str(code or "").strip().replace("_", "-")
    if not tag or len(tag) > MAX_LANGUAGE_CHARS:
        return ""
    parts = tag.split("-")
    language = parts[0].lower()
    if len(parts) > 1:
        regional = f"{language}-{parts[-1].upper()}"
        if regional in _TTS_LANGUAGES:
            return regional
    return _DEFAULT_REGION.get(language, "")


# ── text tidying ────────────────────────────────────────────────────────────

_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_MARKDOWN_RE = re.compile(r"[*_`#>|~]+")
_BULLET_RE = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)
# A Latin sentence ends with punctuation followed by a space; a danda or a CJK
# full stop ends one on its own, with no space to look for.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=[。！？।])\s*")


def plain_speech(text: str) -> str:
    """Strip what a speech voice would read out literally or stumble on."""
    text = _LINK_RE.sub(r"\1", text or "")
    text = _EMOJI_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    return " ".join(text.split())


def _first_sentences(text: str, count: int = 2, max_chars: int = 300) -> str:
    sentences = [part for part in _SENTENCE_SPLIT_RE.split(text) if part]
    return " ".join(sentences[:count])[:max_chars].strip()


def needs_condensing(spoken: str) -> bool:
    """Whether an answer is too long to simply read out as written."""
    return (
        len(spoken.split()) > _SUMMARY_WORD_THRESHOLD
        or len(spoken) > _SUMMARY_CHAR_THRESHOLD
    )


# ── speech to text ──────────────────────────────────────────────────────────

# Structured output rather than a parsing convention: the transcript and the
# language come back in one call, and a transcript that happens to open with
# something resembling a language tag cannot corrupt the parse.
_TRANSCRIPT_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "language": types.Schema(type=types.Type.STRING),
        "text": types.Schema(type=types.Type.STRING),
    },
    required=["language", "text"],
)


def _parse_transcript(raw: Optional[str]) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError):
        # Structured output was asked for, so this is a malformed reply rather
        # than a bare transcript - but treating it as one still answers the
        # user instead of losing the turn.
        return {"text": raw or ""}
    return payload if isinstance(payload, dict) else {"text": str(payload)}


async def transcribe(audio: bytes, mime_type: str, user_id: str, workspace_id: str) -> Transcript:
    """The spoken question as text plus its language, or an empty Transcript
    when nothing intelligible was said."""
    vendor = speech_vendor()
    if vendor == "openai":
        return await _litellm_transcribe(audio, mime_type)
    if vendor != "gemini":
        raise VoiceNotConfigured(_NO_VENDOR)
    response = await _generate(
        TRANSCRIBE_MODELS,
        [VOICE_TRANSCRIBE_PROMPT, types.Part.from_bytes(data=audio, mime_type=mime_type)],
        _text_config(
            temperature=0,
            max_output_tokens=_TRANSCRIBE_MAX_TOKENS,
            response_mime_type="application/json",
            response_schema=_TRANSCRIPT_SCHEMA,
        ),
        user_id,
        workspace_id,
    )
    payload = _parse_transcript(response.text)
    text = " ".join(str(payload.get("text") or "").split()).strip("\"'“” ")
    if not text or text.upper().rstrip(".") == _NO_SPEECH:
        return Transcript("", "")
    return Transcript(text, speech_language(payload.get("language")))


async def spoken_summary(answer: str, user_id: str, workspace_id: str) -> str:
    """A chat answer condensed to one or two sentences meant to be heard, in
    the language the answer itself is written in.

    Uses the ordinary chat LLM when the speech vendor isn't Gemini - any model
    can shorten a paragraph, and it saves requiring a second vendor's key just
    to do it.
    """
    prompt = VOICE_SUMMARY_PROMPT.format(answer=answer[:MAX_SPEAK_CHARS])
    if speech_vendor() == "gemini":
        response = await _generate(
            TEXT_MODELS,
            prompt,
            _text_config(temperature=0.2, max_output_tokens=_SUMMARY_MAX_TOKENS),
            user_id,
            workspace_id,
        )
        raw = response.text or ""
    else:
        raw = await llm_client.LLMClient().agenerate(
            prompt, temperature=0.2, max_tokens=_SUMMARY_MAX_TOKENS,
            user_id=user_id, workspace_id=workspace_id,
        )
    summary = plain_speech(raw)
    return summary or _first_sentences(plain_speech(answer))


# ── the litellm path (every vendor that is not Gemini) ─────────────────────────

_NO_VENDOR = (
    "No speech service is configured. Add a Gemini or OpenAI key, or let the "
    "browser handle speech instead."
)

# Whisper reports the language as an English word rather than a code.
_WHISPER_LANGUAGE_CODES = {
    "arabic": "ar", "bengali": "bn", "chinese": "zh", "dutch": "nl",
    "english": "en", "french": "fr", "german": "de", "hindi": "hi",
    "indonesian": "id", "italian": "it", "japanese": "ja", "korean": "ko",
    "marathi": "mr", "polish": "pl", "portuguese": "pt", "romanian": "ro",
    "russian": "ru", "spanish": "es", "tamil": "ta", "telugu": "te",
    "thai": "th", "turkish": "tr", "ukrainian": "uk", "vietnamese": "vi",
}


def _normalise_language(raw: Optional[str]) -> str:
    value = str(raw or "").strip().lower()
    return speech_language(_WHISPER_LANGUAGE_CODES.get(value, value))


async def _litellm_transcribe(audio: bytes, mime_type: str) -> Transcript:
    key = _vendor_key("openai")
    suffix = (mime_type.split("/")[-1] or "wav").split(";")[0] or "wav"
    last: Optional[Exception] = None
    for model in STT_MODELS:
        try:
            response = await litellm.atranscription(
                model=model,
                file=(f"question.{suffix}", audio, mime_type),
                response_format="verbose_json",
                temperature=0,
                api_key=key,
                timeout=_TEXT_TIMEOUT_MS / 1000,
            )
        except Exception as exc:  # noqa: BLE001 - any failure means try the next id
            last = exc
            logger.warning("Transcription via %s failed: %s", model, exc)
            continue
        text = " ".join(str(getattr(response, "text", "") or "").split()).strip("\"'“” ")
        if not text or text.upper().rstrip(".") == _NO_SPEECH:
            return Transcript("", "")
        return Transcript(text, _normalise_language(getattr(response, "language", "")))
    raise VoiceError(f"The voice service could not be reached ({type(last).__name__}).")


def _binary_content(response) -> bytes:
    """The audio bytes out of whatever shape litellm hands back."""
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    read = getattr(response, "read", None)
    if callable(read):
        value = read()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    return b""


async def _litellm_synthesize(text: str) -> bytes:
    key = _vendor_key("openai")
    last: Optional[Exception] = None
    for model in LITELLM_TTS_MODELS:
        try:
            response = await litellm.aspeech(
                model=model,
                input=text,
                voice=LITELLM_TTS_VOICE,
                response_format="wav",
                api_key=key,
                timeout=_TTS_TIMEOUT_MS / 1000,
            )
        except Exception as exc:  # noqa: BLE001 - any failure means try the next id
            last = exc
            logger.warning("Speech via %s failed: %s", model, exc)
            continue
        audio = _binary_content(response)
        if audio:
            return audio
    if last is None:
        raise VoiceError("The voice service returned no audio.")
    raise VoiceError(f"The voice service could not be reached ({type(last).__name__}).")


# ── text to speech ──────────────────────────────────────────────────────────


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


# Speech for a given sentence never changes, so the slowest call in the chain
# is skipped entirely when an answer is replayed or a chart insight recurs.
# Deliberately small: a couple of sentences of 24 kHz mono is a few hundred KB,
# and this is per-process memory shared by every user.
_TTS_CACHE_ENTRIES = 16
_TTS_CACHE_MAX_BYTES = 1_500_000
_tts_cache: "OrderedDict[Tuple[str, str, str], bytes]" = OrderedDict()


def _cache_key(text: str, language: str) -> Tuple[str, str, str]:
    return (f"{speech_vendor()}:{TTS_VOICE}:{LITELLM_TTS_VOICE}", language, text)


def _cached_audio(text: str, language: str) -> Optional[bytes]:
    key = _cache_key(text, language)
    wav = _tts_cache.get(key)
    if wav is not None:
        _tts_cache.move_to_end(key)
    return wav


def _cache_audio(text: str, language: str, wav: bytes) -> None:
    if len(wav) > _TTS_CACHE_MAX_BYTES:
        return
    key = _cache_key(text, language)
    _tts_cache[key] = wav
    _tts_cache.move_to_end(key)
    while len(_tts_cache) > _TTS_CACHE_ENTRIES:
        _tts_cache.popitem(last=False)


async def synthesize(text: str, user_id: str, workspace_id: str, language: str = "") -> bytes:
    """`text` read aloud, as WAV bytes.

    `language` is a hint only - Gemini infers the language from the text
    itself; the code just stops it hesitating between close neighbours such
    as Hindi and Marathi. It must already have passed speech_language().
    """
    cached = _cached_audio(text, language)
    if cached is not None:
        return cached

    vendor = speech_vendor()
    if vendor == "openai":
        wav = await _litellm_synthesize(text)
        _cache_audio(text, language, wav)
        return wav
    if vendor != "gemini":
        raise VoiceNotConfigured(_NO_VENDOR)

    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
        ),
        **({"language_code": language} if language else {}),
    )
    response = await _generate(
        TTS_MODELS,
        text,
        types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=speech_config,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(timeout=_TTS_TIMEOUT_MS),
        ),
        user_id,
        workspace_id,
    )
    for candidate in response.candidates or []:
        for part in getattr(candidate.content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            if blob and blob.data:
                wav = pcm_to_wav(blob.data, pcm_rate(blob.mime_type))
                _cache_audio(text, language, wav)
                return wav
    raise VoiceError("The voice service returned no audio.")


async def speak(
    text: str,
    kind: Literal["chat", "chart"],
    user_id: str,
    workspace_id: str,
    language: str = "",
) -> Tuple[str, bytes]:
    """(what is said, WAV bytes) for an answer.

    A chart's insight line is already a single sentence computed from the
    drawn data, so it is spoken as-is; a chat answer is condensed first
    unless it is already short enough to hear in full.
    """
    spoken = plain_speech(text)
    if kind == "chat" and needs_condensing(spoken):
        spoken = await spoken_summary(text, user_id, workspace_id)
    if not spoken:
        raise VoiceError("There is nothing to say for this answer.")
    audio = await synthesize(spoken, user_id, workspace_id, language=speech_language(language))
    return spoken, audio
