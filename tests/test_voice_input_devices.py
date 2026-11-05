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


@pytest.mark.parametrize("fallback", [False, True])
def test_recognizer_provides_word_confidence_for_existing_wake_gate(monkeypatch, tmp_path, fallback):
    import json
    from atlas_ai.voice.wake_loop import _wake_phrase
    recognizers = []
    class Recognizer:
        def __init__(self, *args):
            self.words = False
            recognizers.append(self)
        def SetWords(self, enabled):
            self.words = enabled
        def AcceptWaveform(self, data):
            return True
        def Result(self):
            return json.dumps({"text": "atlas wake", "result": [{"conf": .9}, {"conf": .96}] if self.words else []})
    calls = []
    def stream(**kwargs):
        calls.append(kwargs)
        if fallback and len(calls) == 1:
            raise RuntimeError("device disappeared")
        return object()
    monkeypatch.setattr(voice_input, "ensure_vosk_model", lambda: str(tmp_path))
    monkeypatch.setattr(voice_input, "Model", lambda path: object())
    monkeypatch.setattr(voice_input, "KaldiRecognizer", Recognizer)
    monkeypatch.setattr(voice_input.SpeechInput, "_resolve_device", lambda self: (3, 16000))
    monkeypatch.setattr(voice_input.sd, "RawInputStream", stream)
    monkeypatch.setattr(voice_input.sd, "default", SimpleNamespace(device=[3, 4]))
    monkeypatch.setattr(voice_input.sd, "query_devices", lambda *args: {"default_samplerate": 16000})
    speech = voice_input.SpeechInput(SimpleNamespace(audio_sample_rate=16000, audio_block_size=8000))
    speech._queue.put(b"fake audio")
    text, confidence = speech.next_recognition()
    assert all(r.words for r in recognizers)
    assert confidence == pytest.approx(.93)
    assert _wake_phrase(text, confidence=confidence)


def test_invalid_recognition_confidence_does_not_become_a_high_confidence_command():
    import queue
    speech = voice_input.SpeechInput.__new__(voice_input.SpeechInput)
    speech._queue = queue.Queue()
    speech._queue.put(b"fake audio")
    speech._sample_rate = speech._target_sample_rate = 16000
    speech._recognizer = SimpleNamespace(AcceptWaveform=lambda data: True, Result=lambda: '{"text":"atlas wake","result":[{"conf":NaN}]}')
    assert speech.next_recognition() == ("atlas wake", 0.0)
