"""Core package for Fulloch."""

__all__ = [
    "Assistant",
    "AudioCapture",
    "SAMPLE_RATE",
    "SILENCE_THRESHOLD",
    "generate_slm",
    "is_silent",
    "load_asr_model",
    "load_slm",
    "speak_stream",
    "stream_generator",
]


def __getattr__(name):
    """Lazily import core modules to avoid heavy startup side effects."""
    if name in {"AudioCapture", "is_silent", "SAMPLE_RATE", "SILENCE_THRESHOLD"}:
        from .audio import AudioCapture, SAMPLE_RATE, SILENCE_THRESHOLD, is_silent

        mapping = {
            "AudioCapture": AudioCapture,
            "is_silent": is_silent,
            "SAMPLE_RATE": SAMPLE_RATE,
            "SILENCE_THRESHOLD": SILENCE_THRESHOLD,
        }
        return mapping[name]

    if name in {"load_asr_model", "stream_generator"}:
        from .asr import load_asr_model, stream_generator

        mapping = {
            "load_asr_model": load_asr_model,
            "stream_generator": stream_generator,
        }
        return mapping[name]

    if name in {"load_slm", "generate_slm"}:
        from .slm import generate_slm, load_slm

        mapping = {"load_slm": load_slm, "generate_slm": generate_slm}
        return mapping[name]

    if name == "speak_stream":
        from .tts import speak_stream

        return speak_stream

    if name == "Assistant":
        from .assistant import Assistant

        return Assistant

    raise AttributeError(f"module 'core' has no attribute '{name}'")
