from types import SimpleNamespace

import pytest

import atlas_ai.voice.input as voice_input


def resolver(device):
    speech = voice_input.SpeechInput.__new__(voice_input.SpeechInput)
    speech.config = SimpleNamespace(audio_device_name=device, audio_sample_rate=16000)
    return speech


def test_missing_old_machine_microphone_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setattr(voice_input.sd, "default", SimpleNamespace(device=[3, 4]))

    def check(*, device, **kwargs):
        if device != 3:
            raise ValueError("Device is absent")

    monkeypatch.setattr(voice_input.sd, "check_input_settings", check)
    monkeypatch.setattr(voice_input.sd, "query_devices", lambda *args: (_ for _ in ()).throw(ValueError("Device is absent")))
    assert resolver("Old Realtek device")._resolve_device() == (3, 16000)
    assert "using the default input device" in caplog.text


def test_device_native_rate_is_used_when_preferred_rate_is_unsupported(monkeypatch):
    monkeypatch.setattr(voice_input.sd, "default", SimpleNamespace(device=[3, 4]))

    def check(*, samplerate, **kwargs):
        if samplerate != 48000:
            raise ValueError("Unsupported sample rate")

    monkeypatch.setattr(voice_input.sd, "check_input_settings", check)
    monkeypatch.setattr(voice_input.sd, "query_devices", lambda *args: {"default_samplerate": 48000})
    assert resolver("")._resolve_device() == (3, 48000)


def test_no_microphone_reports_a_clear_error_without_opening_a_stream(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ValueError("No devices")

    monkeypatch.setattr(voice_input.sd, "default", SimpleNamespace(device=[-1, -1]))
    monkeypatch.setattr(voice_input.sd, "check_input_settings", unavailable)
    monkeypatch.setattr(voice_input.sd, "query_devices", unavailable)
    with pytest.raises(RuntimeError, match="No usable audio input device"):
        resolver("")._resolve_device()
