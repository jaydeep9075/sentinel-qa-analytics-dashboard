"""Push-to-talk voice: the speech/text helpers and the /voice routes.

Gemini is never called. The network functions in services.voice are
monkeypatched, so these tests pin down the plumbing around them - auth,
quota, size and type limits, response shape, when a chat answer gets
summarised - plus the pure audio and text helpers.
"""

import base64
import importlib
import io
import sys
import wave

import pytest
from fastapi.testclient import TestClient


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


# -------------------- /voice/transcribe --------------------

def test_voice_routes_require_login(client):
    assert client.post("/voice/transcribe", files=_upload(_wav())).status_code in (401, 403)
    assert client.post("/voice/speak", json={"text": "hi"}).status_code in (401, 403)


def test_transcribe_returns_the_question(client, headers, main, monkeypatch):
    seen = {}

    async def fake_transcribe(audio, mime_type, user_id, workspace_id):
        seen.update(mime_type=mime_type, user_id=user_id, size=len(audio))
        return "which tests failed the most"

    monkeypatch.setattr(main.voice, "transcribe", fake_transcribe)
    wav = _wav()
    res = client.post("/voice/transcribe", headers=headers, files=_upload(wav))
    assert res.status_code == 200, res.text
    assert res.json() == {"text": "which tests failed the most"}
    assert seen == {"mime_type": "audio/wav", "user_id": "admin", "size": len(wav)}


def test_transcribe_rejects_non_audio(client, headers):
    res = client.post("/voice/transcribe", headers=headers, files=_upload(b"hello", "text/plain"))
    assert res.status_code == 415


def test_transcribe_rejects_oversized_recording(client, headers, main, monkeypatch):
    monkeypatch.setattr(main.voice, "MAX_AUDIO_BYTES", 100)
    res = client.post("/voice/transcribe", headers=headers, files=_upload(_wav()))
    assert res.status_code == 413


def test_silence_is_a_retry_not_an_empty_question(client, headers, main, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return ""

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

    async def fake_synthesize(text, user_id, workspace_id):
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


def test_voice_respects_the_token_quota(client, headers, main, monkeypatch, fake_tts):
    store = main.get_user_store()
    monkeypatch.setattr(type(store), "get_token_limit", lambda self, username: 10)
    monkeypatch.setattr(main.token_usage_store, "get_lifetime_total", lambda username: 50)
    res = client.post("/voice/speak", headers=headers, json={"text": "hello"})
    assert res.status_code == 429
    assert fake_tts == []
