"""Push-to-talk voice: the speech/text helpers and the /voice routes.

Gemini is never called. The network functions in services.voice are
monkeypatched, so these tests pin down the plumbing around them - auth,
quota, size and type limits, response shape, when a chat answer gets
summarised - plus the pure audio and text helpers.
"""

import asyncio
import base64
import importlib
import io
import sys
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai import types as genai_types

# Any config object will do for the model-selection tests; only its
# thinking_config is ever inspected there.
_CONFIG = genai_types.GenerateContentConfig(temperature=0)


@pytest.fixture()
def main(tmp_path, monkeypatch):
    """services.main on a throwaway state directory (same setup as
    test_auth_default_credentials.py - config reads the environment at import
    time, hence the module purge)."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("STATE_DIR", str(state_dir))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_USER_STORE_URL", f"sqlite:///{(state_dir / 'users.db').as_posix()}")
    monkeypatch.setenv("AUTH_BACKEND", "db")
    monkeypatch.setenv("BCRYPT_ROUNDS", "10")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("AUTO_INGEST_ENABLED", "false")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")

    for name in [m for m in sys.modules if m == "services" or m.startswith("services.")]:
        del sys.modules[name]
    return importlib.import_module("services.main")


@pytest.fixture()
def client(main):
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def headers(client):
    res = client.post("/auth/login", params={"username": "admin", "password": "admin"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _wav(frames: int = 1600, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def _upload(data: bytes, content_type: str = "audio/wav"):
    return {"audio": ("question.wav", data, content_type)}


# -------------------- helpers --------------------

def test_pcm_to_wav_wraps_tts_output_playably(main):
    wav = main.voice.pcm_to_wav(b"\x01\x00" * 240, 24000)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (24000, 1, 2, 240)


def test_pcm_rate_reads_both_tts_mime_formats(main):
    # The two TTS models disagree on how they spell the same thing.
    assert main.voice.pcm_rate("audio/L16;codec=pcm;rate=24000") == 24000
    assert main.voice.pcm_rate("audio/l16; rate=16000; channels=1") == 16000
    assert main.voice.pcm_rate(None) == 24000


def test_plain_speech_drops_what_a_voice_would_read_literally(main):
    text = "📊 **Pass rate:** 92%\n- [Checkout suite](http://x) has `3` failures"
    assert main.voice.plain_speech(text) == "Pass rate: 92% Checkout suite has 3 failures"


def test_plain_speech_leaves_non_latin_scripts_alone(main):
    # The markdown/emoji strippers must not eat the answer itself when it is
    # written in Devanagari, Japanese or Arabic.
    assert main.voice.plain_speech("**पास दर 92% है।**") == "पास दर 92% है।"
    assert main.voice.plain_speech("合格率は92%です。") == "合格率は92%です。"


def test_speech_language_only_passes_tags_the_tts_api_accepts(main):
    # A bare code is expanded to the region its voices exist for...
    assert main.voice.speech_language("hi") == "hi-IN"
    assert main.voice.speech_language("en") == "en-US"
    assert main.voice.speech_language("en-IN") == "en-IN"
    assert main.voice.speech_language("pt_BR") == "pt-BR"
    # ...and anything unsupported becomes "", which means "infer it from the
    # words" rather than an outright API error.
    assert main.voice.speech_language("zz-ZZ") == ""
    assert main.voice.speech_language(None) == ""


def test_answers_without_spaces_are_still_recognised_as_too_long(main):
    # Japanese and Thai have no word boundaries, so a word count alone would
    # send a whole paragraph to the speech model unabridged.
    assert not main.voice.needs_condensing("合格率は92%です。")
    assert main.voice.needs_condensing("テストが失敗しました。" * 30)


def test_key_comes_from_active_gemini_settings(main, monkeypatch):
    monkeypatch.setattr(
        main.voice.app_settings, "get_llm_settings",
        lambda include_secret=False: {"provider": "gemini", "api_key": "from-settings"},
    )
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert main.voice._gemini_api_key() == "from-settings"


def test_another_providers_key_is_never_sent_to_gemini(main, monkeypatch):
    monkeypatch.setattr(
        main.voice.app_settings, "get_llm_settings",
        lambda include_secret=False: {"provider": "openai", "api_key": "sk-openai"},
    )
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert main.voice._gemini_api_key() == "from-env"

    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(main.voice.VoiceNotConfigured):
        main.voice._gemini_api_key()


# -------------------- choosing a model --------------------

def _fake_client(main, monkeypatch, handler):
    """A genai client whose generate_content is `handler`."""
    models = SimpleNamespace(generate_content=handler)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(main.voice, "_client", lambda: client)
    monkeypatch.setattr(main.voice, "_record_usage", lambda *a, **k: None)
    main.voice._resolved_model.clear()
    return client


def _client_error(main, code, message):
    return genai_errors.ClientError(
        code, {"error": {"code": code, "message": message, "status": "NOT_FOUND"}}
    )


def test_a_retired_model_id_falls_through_to_one_that_works(main, monkeypatch):
    # The whole point of the candidate list: a model being renamed or pulled
    # must cost one failed call, not the entire voice feature.
    calls = []

    async def handler(model, contents, config):
        calls.append(model)
        if model == "dead-model":
            raise _client_error(main, 404, "models/dead-model is not found")
        return SimpleNamespace(text="ok", usage_metadata=None)

    _fake_client(main, monkeypatch, handler)
    models = ("dead-model", "live-model")

    response = asyncio.run(main.voice._generate(models, "hi", _CONFIG, "u", "w"))
    assert response.text == "ok"
    assert calls == ["dead-model", "live-model"]

    # ...and the dead one is not tried again for the rest of the process.
    calls.clear()
    asyncio.run(main.voice._generate(models, "hi", _CONFIG, "u", "w"))
    assert calls == ["live-model"]


def test_a_rate_limit_does_not_burn_through_the_other_models(main, monkeypatch):
    calls = []

    async def handler(model, contents, config):
        calls.append(model)
        raise genai_errors.ClientError(
            429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}}
        )

    _fake_client(main, monkeypatch, handler)
    with pytest.raises(main.voice.VoiceError):
        asyncio.run(main.voice._generate(("first", "second"), "hi", _CONFIG, "u", "w"))
    assert calls == ["first"]


def test_a_model_that_rejects_the_request_falls_through_too(main, monkeypatch):
    # The failure that took voice down: a model that answers text but refuses
    # an audio part says only "400 INVALID_ARGUMENT", with nothing naming
    # itself. Treating that as fatal stopped the search at the first candidate
    # while two working ones sat behind it.
    calls = []

    async def handler(model, contents, config):
        calls.append(model)
        if model == "text-only":
            raise genai_errors.ClientError(
                400,
                {"error": {"code": 400, "message": "Request contains an invalid argument.",
                           "status": "INVALID_ARGUMENT"}},
            )
        return SimpleNamespace(text="ok", usage_metadata=None)

    _fake_client(main, monkeypatch, handler)
    assert asyncio.run(
        main.voice._generate(("text-only", "hears-audio"), "hi", _CONFIG, "u", "w")
    ).text == "ok"
    assert calls == ["text-only", "hears-audio"]


def test_a_remembered_model_that_starts_failing_is_forgotten(main, monkeypatch):
    # Otherwise the memo pins the search to a model that no longer works and
    # every later request pays the same wasted call.
    async def handler(model, contents, config):
        if model == "flaky":
            raise genai_errors.ClientError(
                400, {"error": {"code": 400, "message": "nope", "status": "INVALID_ARGUMENT"}}
            )
        return SimpleNamespace(text="ok", usage_metadata=None)

    _fake_client(main, monkeypatch, handler)
    models = ("flaky", "solid")
    main.voice._resolved_model[models] = "flaky"

    assert asyncio.run(main.voice._generate(models, "hi", _CONFIG, "u", "w")).text == "ok"
    assert main.voice._resolved_model[models] == "solid"


def test_hearing_and_summarising_use_separate_model_chains(main):
    # Sharing one list made the fallback unwinnable: whichever model the last
    # summary settled on was tried first for the next question's audio, and
    # answering text is no promise of accepting audio.
    assert main.voice.TRANSCRIBE_MODELS != main.voice.TEXT_MODELS


def test_an_overloaded_service_is_retried_once(main, monkeypatch):
    calls = []

    async def handler(model, contents, config):
        calls.append(model)
        raise genai_errors.ServerError(
            503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
        )

    _fake_client(main, monkeypatch, handler)
    monkeypatch.setattr(main.voice, "_RETRY_DELAY_SECONDS", 0)
    with pytest.raises(main.voice.VoiceError):
        asyncio.run(main.voice._generate(("only",), "hi", _CONFIG, "u", "w"))
    assert calls == ["only", "only"]


def test_a_model_that_demands_thinking_is_asked_again_without_it(main, monkeypatch):
    # Disabling thinking is a latency optimisation; a model that rejects it
    # must still answer the question.
    seen = []

    async def handler(model, contents, config):
        seen.append(config.thinking_config)
        if config.thinking_config is not None:
            raise genai_errors.ClientError(
                400,
                {"error": {"code": 400, "message": "thinking_budget 0 is not supported", "status": "INVALID_ARGUMENT"}},
            )
        return SimpleNamespace(text="ok", usage_metadata=None)

    _fake_client(main, monkeypatch, handler)
    main.voice._rejects_thinking.clear()
    config = main.voice._text_config(temperature=0, max_output_tokens=16)

    assert asyncio.run(main.voice._generate(("picky",), "hi", config, "u", "w")).text == "ok"
    assert [c is None for c in seen] == [False, True]
    assert "picky" in main.voice._rejects_thinking
    # The original config is not mutated - the next model still gets the fast path.
    assert config.thinking_config is not None


# -------------------- choosing a speech vendor --------------------
# Speech is a separate axis from the chat LLM: Anthropic has no speech API at
# all, so a Claude-only deployment must fall back to the browser rather than
# lose the mic.

@pytest.fixture()
def no_vendor_keys(main, monkeypatch):
    monkeypatch.setattr(
        main.voice.app_settings, "get_llm_settings",
        lambda include_secret=False: {"provider": "", "api_key": ""},
    )
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(main.voice, "SPEECH_PROVIDER", "auto")


def test_gemini_key_selects_gemini(main, monkeypatch, no_vendor_keys):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert main.voice.speech_vendor() == "gemini"
    assert main.voice.capabilities() == {"mode": "server", "provider": "gemini"}


def test_an_openai_only_deployment_uses_openai_for_speech(main, monkeypatch, no_vendor_keys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert main.voice.speech_vendor() == "openai"
    assert main.voice.capabilities() == {"mode": "server", "provider": "openai"}


def test_a_claude_only_deployment_falls_back_to_the_browser(main, monkeypatch, no_vendor_keys):
    # Anthropic ships no transcription or TTS endpoint, so there is nothing to
    # call - the browser does the speech instead of the mic disappearing.
    monkeypatch.setattr(
        main.voice.app_settings, "get_llm_settings",
        lambda include_secret=False: {"provider": "anthropic", "api_key": "sk-ant"},
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    assert main.voice.speech_vendor() == ""
    assert main.voice.capabilities() == {"mode": "browser", "provider": None}


def test_the_chat_provider_is_preferred_when_both_keys_exist(main, monkeypatch, no_vendor_keys):
    monkeypatch.setattr(
        main.voice.app_settings, "get_llm_settings",
        lambda include_secret=False: {"provider": "openai", "api_key": "sk-openai"},
    )
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert main.voice.speech_vendor() == "openai"


def test_voice_provider_browser_forces_local_speech(main, monkeypatch, no_vendor_keys):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setattr(main.voice, "SPEECH_PROVIDER", "browser")
    assert main.voice.speech_vendor() == ""
    assert main.voice.capabilities()["mode"] == "browser"


def test_capabilities_endpoint_tells_the_browser_which_half_speaks(client, headers, main, monkeypatch):
    monkeypatch.setattr(main.voice, "capabilities", lambda: {"mode": "browser", "provider": None})
    res = client.get("/voice/capabilities", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json() == {"mode": "browser", "provider": None}


def test_capabilities_requires_login(client):
    assert client.get("/voice/capabilities").status_code in (401, 403)


def test_transcribing_without_a_vendor_is_reported_as_unavailable(client, headers, main, monkeypatch):
    monkeypatch.setattr(main.voice, "speech_vendor", lambda: "")
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 503


# -------------------- /voice/transcribe --------------------

def test_voice_routes_require_login(client):
    assert client.post("/voice/transcribe", files=_upload(_wav())).status_code in (401, 403)
    assert client.post("/voice/speak", json={"text": "hi"}).status_code in (401, 403)


def test_transcribe_returns_the_question(client, headers, main, monkeypatch):
    seen = {}

    async def fake_transcribe(audio, mime_type, user_id, workspace_id):
        seen.update(mime_type=mime_type, user_id=user_id, size=len(audio))
        return main.voice.Transcript("which tests failed the most", "en-US")

    monkeypatch.setattr(main.voice, "transcribe", fake_transcribe)
    wav = _wav()
    res = client.post("/voice/transcribe", headers=headers, files=_upload(wav))
    assert res.status_code == 200, res.text
    assert res.json() == {"text": "which tests failed the most", "language": "en-US"}
    assert seen == {"mime_type": "audio/wav", "user_id": "admin", "size": len(wav)}


def test_transcribe_carries_the_spoken_language_back(client, headers, main, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return main.voice.Transcript("कितने टेस्ट फेल हुए", "hi-IN")

    monkeypatch.setattr(main.voice, "transcribe", fake_transcribe)
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 200, res.text
    assert res.json() == {"text": "कितने टेस्ट फेल हुए", "language": "hi-IN"}


def test_transcribe_rejects_non_audio(client, headers):
    res = client.post("/voice/transcribe", headers=headers, files=_upload(b"hello", "text/plain"))
    assert res.status_code == 415


def test_transcribe_rejects_oversized_recording(client, headers, main, monkeypatch):
    monkeypatch.setattr(main.voice, "MAX_AUDIO_BYTES", 100)
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 413


def test_silence_is_a_retry_not_an_empty_question(client, headers, main, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return main.voice.Transcript("", "")

    monkeypatch.setattr(main.voice, "transcribe", fake_transcribe)
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 422
    assert "catch" in res.json()["detail"]


def test_missing_gemini_key_is_reported_as_unavailable(client, headers, main, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        raise main.voice.VoiceNotConfigured("Voice needs a Gemini API key.")

    monkeypatch.setattr(main.voice, "transcribe", fake_transcribe)
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 503
    assert "Gemini" in res.json()["detail"]


# -------------------- /voice/speak --------------------

@pytest.fixture()
def fake_tts(main, monkeypatch):
    spoken = []

    async def fake_synthesize(text, user_id, workspace_id, language=""):
        spoken.append(text)
        return b"RIFF-fake-wav"

    monkeypatch.setattr(main.voice, "synthesize", fake_synthesize)
    return spoken


def test_chart_insight_is_spoken_as_is(client, headers, main, monkeypatch, fake_tts):
    async def no_summary(*args, **kwargs):
        raise AssertionError("a chart insight must not be summarised")

    monkeypatch.setattr(main.voice, "spoken_summary", no_summary)
    res = client.post(
        "/voice/speak", headers=headers,
        json={"text": "**Failed** leads with 42% of tests.", "kind": "chart"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["spoken_text"] == "Failed leads with 42% of tests."
    assert base64.b64decode(body["audio"]) == b"RIFF-fake-wav"
    assert body["mime_type"] == "audio/wav"


def test_long_chat_answer_is_summarised_before_speaking(client, headers, main, monkeypatch, fake_tts):
    async def fake_summary(answer, user_id, workspace_id):
        return "Pass rate is 92 percent."

    monkeypatch.setattr(main.voice, "spoken_summary", fake_summary)
    long_answer = "### Summary\n" + "The checkout suite had several failures today. " * 10
    res = client.post("/voice/speak", headers=headers, json={"text": long_answer, "kind": "chat"})
    assert res.status_code == 200, res.text
    assert res.json()["spoken_text"] == "Pass rate is 92 percent."
    assert fake_tts == ["Pass rate is 92 percent."]


def test_short_chat_answer_skips_the_summary_round_trip(client, headers, main, monkeypatch, fake_tts):
    async def no_summary(*args, **kwargs):
        raise AssertionError("a short answer is already speakable")

    monkeypatch.setattr(main.voice, "spoken_summary", no_summary)
    res = client.post("/voice/speak", headers=headers, json={"text": "✅ **All 120 tests passed.**"})
    assert res.status_code == 200, res.text
    assert res.json()["spoken_text"] == "All 120 tests passed."


def test_speak_rejects_oversized_text(client, headers, main):
    res = client.post("/voice/speak", headers=headers, json={"text": "a" * (main.voice.MAX_SPEAK_CHARS + 1)})
    assert res.status_code == 422


def test_the_spoken_language_reaches_the_speech_model(client, headers, main, monkeypatch):
    seen = {}

    async def fake_synthesize(text, user_id, workspace_id, language=""):
        seen["language"] = language
        return b"RIFF-fake-wav"

    monkeypatch.setattr(main.voice, "synthesize", fake_synthesize)
    res = client.post(
        "/voice/speak", headers=headers,
        json={"text": "पास दर 92% है।", "kind": "chat", "language": "hi"},
    )
    assert res.status_code == 200, res.text
    assert seen["language"] == "hi-IN"


def test_an_unsupported_language_is_dropped_rather_than_sent(client, headers, main, monkeypatch):
    # Passing a tag the TTS API doesn't know is a hard error, so the hint is
    # discarded and the model infers the language from the text instead.
    seen = {}

    async def fake_synthesize(text, user_id, workspace_id, language=""):
        seen["language"] = language
        return b"RIFF-fake-wav"

    monkeypatch.setattr(main.voice, "synthesize", fake_synthesize)
    res = client.post(
        "/voice/speak", headers=headers,
        json={"text": "All good.", "language": "klingon"},
    )
    assert res.status_code == 200, res.text
    assert seen["language"] == ""


def test_voice_respects_the_token_quota(client, headers, main, monkeypatch, fake_tts):
    store = main.get_user_store()
    monkeypatch.setattr(type(store), "get_token_limit", lambda self, username: 10)
    monkeypatch.setattr(main.token_usage_store, "get_lifetime_total", lambda username: 50)
    res = client.post("/voice/speak", headers=headers, json={"text": "hello"})
    assert res.status_code == 429
    assert fake_tts == []
