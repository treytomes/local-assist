"""
In-process local TTS/STT using kokoro and faster-whisper.

TTS: kokoro KPipeline — downloads voice .pt files from HuggingFace on first use.
     Voices prefixed 'a' → American English, 'b' → British English.

STT: faster-whisper WhisperModel — available model sizes:
     tiny, tiny.en, base, base.en, small, small.en,
     medium, medium.en, large-v1, large-v2, large-v3

Models are loaded lazily on first call and kept as module-level singletons.
"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
from typing import Iterator

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — overridable by callers (e.g. tests, settings endpoints)
# ---------------------------------------------------------------------------

WHISPER_MODEL_SIZE: str = "base.en"

VOICES = (
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael",
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
)

WHISPER_MODELS = (
    "tiny.en", "tiny",
    "base.en", "base",
    "small.en", "small",
    "medium.en", "medium",
    "large-v1", "large-v2", "large-v3",
)

# ---------------------------------------------------------------------------
# Singletons and lifecycle
# ---------------------------------------------------------------------------

_tts_lock = threading.Lock()
_tts_pipeline_a = None   # American English KPipeline
_tts_pipeline_b = None   # British English KPipeline
_tts_available: bool | None = None

_stt_lock = threading.Lock()
_stt_model = None
_stt_model_size: str = ""
_stt_available: bool | None = None


def _get_tts() -> tuple:
    """Return (pipeline_a, pipeline_b), loading on first call."""
    global _tts_pipeline_a, _tts_pipeline_b, _tts_available
    with _tts_lock:
        if _tts_pipeline_a is None:
            try:
                from kokoro import KPipeline
                _tts_pipeline_a = KPipeline(lang_code='a')
                _tts_pipeline_b = KPipeline(lang_code='b')
                _tts_available = True
                logger.info("Kokoro TTS pipelines loaded")
            except Exception as exc:
                _tts_available = False
                raise RuntimeError(f"Failed to load Kokoro TTS: {exc}") from exc
        return _tts_pipeline_a, _tts_pipeline_b


def _get_stt():
    """Return WhisperModel, loading on first call or if model size changed."""
    global _stt_model, _stt_model_size, _stt_available
    with _stt_lock:
        if _stt_model is None or _stt_model_size != WHISPER_MODEL_SIZE:
            try:
                from faster_whisper import WhisperModel
                logger.info("Loading Whisper model '%s'…", WHISPER_MODEL_SIZE)
                _stt_model = WhisperModel(
                    WHISPER_MODEL_SIZE,
                    device="cpu",
                    compute_type="int8",
                )
                _stt_model_size = WHISPER_MODEL_SIZE
                _stt_available = True
                logger.info("Whisper model '%s' loaded", WHISPER_MODEL_SIZE)
            except Exception as exc:
                _stt_available = False
                raise RuntimeError(f"Failed to load Whisper model '{WHISPER_MODEL_SIZE}': {exc}") from exc
        return _stt_model


def unload_stt() -> None:
    """Release the Whisper model from memory (e.g. before switching sizes)."""
    global _stt_model, _stt_available
    with _stt_lock:
        _stt_model = None
        _stt_available = None


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

async def health_check_tts() -> bool:
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _probe_tts)
    except Exception:
        return False


async def health_check_stt() -> bool:
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _probe_stt)
    except Exception:
        return False


def _probe_tts() -> bool:
    global _tts_available
    if _tts_available is not None:
        return _tts_available
    try:
        import kokoro  # noqa: F401
        return True
    except ImportError:
        _tts_available = False
        return False


def _probe_stt() -> bool:
    global _stt_available
    if _stt_available is not None:
        return _stt_available
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        _stt_available = False
        return False


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

def _pcm_to_mp3(samples: np.ndarray, sample_rate: int = 24000) -> bytes:
    """Convert float32 PCM samples to MP3 bytes via soundfile + lameenc or fallback to WAV."""
    # Clamp to [-1, 1] and convert to int16
    samples = np.clip(samples, -1.0, 1.0)
    pcm_int16 = (samples * 32767).astype(np.int16)

    try:
        import lameenc
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(128)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(1)
        encoder.set_quality(2)
        mp3_data = encoder.encode(pcm_int16.tobytes())
        mp3_data += encoder.flush()
        return bytes(mp3_data)
    except ImportError:
        pass

    # Fallback: return WAV (browsers handle it fine)
    buf = io.BytesIO()
    import soundfile as sf
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _synthesize_sync(text: str, voice: str, speed: float) -> bytes:
    pipeline_a, pipeline_b = _get_tts()
    if voice not in VOICES:
        voice = "af_heart"

    # British voices start with 'b', American with 'a'
    pipeline = pipeline_b if voice.startswith('b') else pipeline_a

    chunks: list[np.ndarray] = []
    for result in pipeline(text, voice=voice, speed=speed):
        audio = result.audio
        if audio is not None:
            arr = audio.numpy() if hasattr(audio, 'numpy') else np.array(audio)
            chunks.append(arr)

    if not chunks:
        raise RuntimeError("Kokoro TTS produced no audio output")

    combined = np.concatenate(chunks)
    return _pcm_to_mp3(combined, sample_rate=24000)


async def synthesize(text: str, voice: str = "af_heart", speed: float = 1.0) -> bytes:
    """Synthesize text to MP3 via in-process Kokoro TTS."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _synthesize_sync, text, voice, max(0.5, min(2.0, speed)))


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def _transcribe_sync(audio_bytes: bytes, filename: str) -> str:
    model = _get_stt()

    # faster-whisper can transcribe from a numpy array; decode audio bytes first
    import soundfile as sf
    buf = io.BytesIO(audio_bytes)
    try:
        samples, sr = sf.read(buf, dtype="float32", always_2d=False)
    except Exception:
        # soundfile can't read webm; try ffmpeg via subprocess
        samples, sr = _decode_with_ffmpeg(audio_bytes)

    # Resample to 16 kHz if needed (faster-whisper expects 16000 Hz)
    if sr != 16000:
        samples = _resample(samples, sr, 16000)

    segments, _ = model.transcribe(samples, language="en", beam_size=5, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _decode_with_ffmpeg(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode any audio format to float32 PCM via ffmpeg."""
    import subprocess
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        tmp_in = f.name
    tmp_out = tmp_in + ".pcm"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in, "-f", "f32le", "-ar", "16000", "-ac", "1", tmp_out],
            check=True, capture_output=True,
        )
        samples = np.frombuffer(open(tmp_out, "rb").read(), dtype=np.float32)
        return samples, 16000
    finally:
        os.unlink(tmp_in)
        if os.path.exists(tmp_out):
            os.unlink(tmp_out)


def _resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resample for mono audio."""
    if orig_sr == target_sr:
        return samples
    ratio = target_sr / orig_sr
    new_len = int(len(samples) * ratio)
    return np.interp(
        np.linspace(0, len(samples) - 1, new_len),
        np.arange(len(samples)),
        samples,
    ).astype(np.float32)


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio bytes via in-process faster-whisper."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, audio_bytes, filename)


# ---------------------------------------------------------------------------
# Model management helpers (called from main.py settings endpoints)
# ---------------------------------------------------------------------------

def get_stt_model_size() -> str:
    return WHISPER_MODEL_SIZE


def set_stt_model_size(size: str) -> None:
    global WHISPER_MODEL_SIZE
    if size not in WHISPER_MODELS:
        raise ValueError(f"Unknown model size '{size}'. Valid: {WHISPER_MODELS}")
    if size != WHISPER_MODEL_SIZE:
        unload_stt()
        WHISPER_MODEL_SIZE = size


def is_stt_loaded() -> bool:
    return _stt_model is not None


def is_tts_loaded() -> bool:
    return _tts_pipeline_a is not None
