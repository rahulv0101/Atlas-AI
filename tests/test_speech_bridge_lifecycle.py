import threading
from unittest.mock import Mock

from atlas_ai.voice.output import SpeechOutput


def test_unused_speech_output_does_not_create_a_background_thread(monkeypatch):
    monkeypatch.setenv("ATLAS_TTS_ENABLED","false")
    monkeypatch.setenv("ATLAS_AUDIO_BRIDGE_SEND_ENABLED","true")
    worker=Mock();factory=Mock(return_value=worker)
    monkeypatch.setattr("atlas_ai.voice.output.threading.Thread",factory)
    output=SpeechOutput()
    factory.assert_not_called()
    output.speak("")
    factory.assert_not_called()
    output.speak("Ready")
    output.speak("Listening")
    assert factory.call_count==1 and worker.start.call_count==1
    assert list(output._bridge_queue.queue)==["Ready","Listening"]


def test_concurrent_bridge_start_has_one_worker(monkeypatch):
    monkeypatch.setenv("ATLAS_TTS_ENABLED","false")
    monkeypatch.setenv("ATLAS_AUDIO_BRIDGE_SEND_ENABLED","true")
    output=SpeechOutput()
    callers=[threading.Thread(target=output._ensure_bridge_thread) for _ in range(8)]
    worker=Mock();factory=Mock(return_value=worker)
    monkeypatch.setattr("atlas_ai.voice.output.threading.Thread",factory)
    for caller in callers:caller.start()
    for caller in callers:
        caller.join(timeout=2)
        assert not caller.is_alive()
    assert factory.call_count==1 and worker.start.call_count==1
