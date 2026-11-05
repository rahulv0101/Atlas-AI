from __future__ import annotations

import json
import logging
import math
import queue
import warnings
from dataclasses import dataclass
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from atlas_ai.atlas_vosk_setup import ensure_vosk_model
from atlas_ai.atlas_wake_config import AtlasWakeConfig

with warnings.catch_warnings():
    # TODO(py3.13): replace audioop.ratecv with a Python 3.13-safe resampler.
    warnings.filterwarnings(
        "ignore",
        message=".*audioop.*deprecated.*",
        category=DeprecationWarning,
    )
    import audioop  # type: ignore[import-not-found]


@dataclass
class SpeechInput:
    config: AtlasWakeConfig

    def __post_init__(self) -> None:
        model_path = Path(ensure_vosk_model())
        self._target_sample_rate = int(self.config.audio_sample_rate or 16000)
        self._device, self._sample_rate = self._resolve_device()
        self._resample_state = None
        self._model = Model(str(model_path))
        self._recognizer = KaldiRecognizer(self._model, float(self._target_sample_rate))
        self._recognizer.SetWords(True)
        self._queue: queue.Queue[bytes] = queue.Queue()
        try:
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                blocksize=self.config.audio_block_size,
                dtype="int16",
                channels=1,
                callback=self._callback,
                device=self._device,
            )
        except Exception:
            default_device = sd.default.device[0]
            info = sd.query_devices(default_device, "input")
            self._device = default_device
            self._sample_rate = int(float(info["default_samplerate"]))
            self._recognizer = KaldiRecognizer(self._model, float(self._target_sample_rate))
            self._recognizer.SetWords(True)
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                blocksize=self.config.audio_block_size,
                dtype="int16",
                channels=1,
                callback=self._callback,
                device=self._device,
            )

    def _resolve_device(self) -> tuple[str | int | None, int]:
        preferred_rate = int(self.config.audio_sample_rate or 16000)
        default_device = sd.default.device[0]
        requested = self.config.audio_device_name or default_device
        candidates = [requested] + ([default_device] if requested != default_device else [])
        last_error = None
        for device in candidates:
            try:
                sd.check_input_settings(device=device, samplerate=preferred_rate, channels=1, dtype="int16")
                rate = preferred_rate
            except Exception as exc:
                last_error = exc
                try:
                    info = sd.query_devices(device, "input")
                    rate = int(float(info["default_samplerate"]))
                    sd.check_input_settings(device=device, samplerate=rate, channels=1, dtype="int16")
                except Exception as exc:
                    last_error = exc
                    continue
            if device != requested:
                logging.getLogger(__name__).warning("Configured audio input is unavailable; using the default input device.")
            return device, rate
        raise RuntimeError("No usable audio input device is available") from last_error

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        self._queue.put(bytes(indata))

    def __enter__(self) -> "SpeechInput":
        self._stream.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self._stream.stop()
        self._stream.close()

    def next_recognition(self) -> tuple[str, float]:
        data = self._queue.get()
        if self._sample_rate != self._target_sample_rate:
            data, self._resample_state = audioop.ratecv(
                data,
                2,
                1,
                self._sample_rate,
                self._target_sample_rate,
                self._resample_state,
            )
        if self._recognizer.AcceptWaveform(data):
            payload = json.loads(self._recognizer.Result())
            text = str(payload.get("text", "") or "").strip()
            conf = 0.0
            words = list(payload.get("result", []) or [])
            if words:
                vals = []
                for row in words:
                    try:
                        value = float(row.get("conf", 0.0) or 0.0)
                        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                            return text, 0.0
                        vals.append(value)
                    except Exception:
                        continue
                if vals:
                    conf = max(0.0, min(1.0, sum(vals) / len(vals)))
            return text, conf
        return "", 0.0

    def next_text(self) -> str:
        text, _ = self.next_recognition()
        return text
