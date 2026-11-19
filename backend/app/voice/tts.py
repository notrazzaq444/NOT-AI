"""Text-to-Speech engine using Fish Audio (voice clone)."""
from fishaudio import AsyncFishAudio
from app.config.settings import get_settings

async def generate_speech(text: str, voice: str | None = None) -> bytes:
    settings = get_settings()
    api_key = settings.fish_api_key
    voice_id = voice or settings.fish_voice_id
    
    if not api_key or not voice_id:
        print("[TTS] Fish Audio key ya voice ID missing hai!")
        return b""
        
    client = AsyncFishAudio(api_key=api_key)
    print(f"[TTS] Generating audio for: {text[:30]}...")
    
    try:
        # Text ko saaf karein (taake special characters se crash na ho)
        clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
        if not clean_text:
            return b""

        # Fish Audio se audio generate karein
        audio_bytes = await client.tts.convert(
            text=clean_text,
            reference_id=voice_id,
            model="s2.1-pro-free",
            format="mp3",
            latency="balanced" 
        )
        
        print(f"[TTS] Success: {len(audio_bytes)} bytes")
        return audio_bytes
        
    except Exception as e:
        print(f"❌ [TTS] Fish Audio Error: {e}")
        return b""