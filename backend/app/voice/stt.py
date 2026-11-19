"""Fast Speech-to-Text with VAD."""
from __future__ import annotations

class SpeechToText:
    def __init__(self, model_size="tiny"):  # base → tiny (fast!)
        self.model_size = model_size
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            print(f"[STT] Loading Whisper model: {self.model_size}")
            # CPU par int8 use karein, yeh sabse fast hai
            self._model = WhisperModel(
                self.model_size, 
                device="cpu", 
                compute_type="int8",
                cpu_threads=4 # CPU cores utilize karein
            )
        return self._model

    def transcribe(self, audio_path: str, language: str | None = None) -> str:
        model = self._load()
        
        supported = {"en", "ur", "hi", "ar", "es", "fr", "de", "zh", "mr"}
        if language not in supported:
            language = None
        
        # Speed settings
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=1,                # 5 se 1 karein (fastest search)
            best_of=1,                  # 5 se 1 karein
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300) # 500 se 300 (fast end)
        )
        
        text = " ".join(segment.text.strip() for segment in segments).strip()
        print(f"[STT] Detected Language: {info.language}, Text: '{text}'")
        return text