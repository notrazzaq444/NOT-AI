window.NOTAudio = (function () {
  let mediaRecorder = null;
  let audioChunks = [];
  let stream = null;
  let audioContext = null;
  let analyser = null;
  let dataArray = null;
  let currentAudio = null;
  let currentAudioUrl = null;
  let onResult = null;
  let isRecording = false;
  let isSpeaking = false;
  let autoContinue = false;
  let silenceFrame = 0;
  let lastVoiceTime = 0;

  function authToken() {
    return localStorage.getItem("firebase_id_token") || "";
  }

  async function initAudioContext() {
    if (!audioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) throw new Error("AudioContext is not supported.");
      audioContext = new AudioContextClass();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      dataArray = new Uint8Array(analyser.frequencyBinCount);
    }
    if (audioContext.state === "suspended") await audioContext.resume();
  }

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent("not:" + name, { detail }));
  }

  function cleanupMic() {
    if (silenceFrame) cancelAnimationFrame(silenceFrame);
    silenceFrame = 0;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    mediaRecorder = null;
    isRecording = false;
    emit("listening", false);
  }

  async function startListening(callback, options = {}) {
    if (isRecording) return true;
    if (typeof callback === "function") onResult = callback;
    if (!authToken()) {
      emit("error", "Please sign in before using voice.");
      return false;
    }

    try {
      await initAudioContext();
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      audioChunks = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size) audioChunks.push(event.data);
      };
      mediaRecorder.onerror = (event) => {
        console.error("[NOT voice] Recorder error:", event.error);
        emit("error", "Microphone recording failed.");
        cleanupMic();
      };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(audioChunks, { type: mediaRecorder?.mimeType || "audio/webm" });
        const token = authToken();
        try {
          if (blob.size) {
            const form = new FormData();
            form.append("audio", blob, "not-voice.webm");
            const language = localStorage.getItem("not-lang") || "en";
            const response = await fetch("/api/transcribe?language=" + encodeURIComponent(language), {
              method: "POST",
              headers: { Authorization: "Bearer " + token },
              body: form,
            });
            if (!response.ok) {
              const body = await response.json().catch(() => ({}));
              throw new Error(body.detail || "Transcription failed (" + response.status + ")");
            }
            const result = await response.json();
            if (result.text && onResult) onResult(result.text);
          }
        } catch (error) {
          console.error("[NOT STT]", error);
          emit("error", error.message || "Could not transcribe audio.");
        } finally {
          cleanupMic();
          if (autoContinue && options.keepListeningAfterEmpty && !isSpeaking) {
            startListening(onResult);
          }
        }
      };

      isRecording = true;
      autoContinue = options.autoContinue !== false;
      lastVoiceTime = Date.now();
      mediaRecorder.start(250);
      emit("listening", true);
      monitorSilence();
      return true;
    } catch (error) {
      cleanupMic();
      console.error("[NOT microphone]", error);
      emit("error", error.name === "NotAllowedError"
        ? "Microphone permission was denied."
        : (error.message || "Could not start microphone."));
      return false;
    }
  }

  function monitorSilence() {
    if (!isRecording || !analyser) return;
    analyser.getByteFrequencyData(dataArray);
    let total = 0;
    for (let i = 0; i < dataArray.length; i++) total += dataArray[i];
    const average = total / dataArray.length;

    if (average > 9) {
      lastVoiceTime = Date.now();
    } else if (Date.now() - lastVoiceTime > 1100) {
      stopRecording(true);
      return;
    }
    silenceFrame = requestAnimationFrame(monitorSilence);
  }

  function stopRecording(keepConversation) {
    if (!isRecording || !mediaRecorder) return;
    if (!keepConversation) autoContinue = false;
    if (mediaRecorder.state !== "inactive") mediaRecorder.stop();
    if (silenceFrame) cancelAnimationFrame(silenceFrame);
    silenceFrame = 0;
  }

  function stopListening() {
    autoContinue = false;
    stopRecording(false);
  }

  async function speak(text, voice) {
    if (!text || !text.trim() || !authToken()) return;
    interrupt();
    try {
      const params = new URLSearchParams({ text });
      if (voice) params.set("voice", voice);
      const response = await fetch("/api/tts?" + params.toString(), {
        headers: { Authorization: "Bearer " + authToken() },
      });
      if (!response.ok) throw new Error("Speech generation failed (" + response.status + ")");
      const blob = await response.blob();
      if (!blob.size) return;

      currentAudioUrl = URL.createObjectURL(blob);
      currentAudio = new Audio(currentAudioUrl);
      isSpeaking = true;
      emit("speaking", true);
      currentAudio.onended = finishSpeaking;
      currentAudio.onerror = finishSpeaking;
      await currentAudio.play();
    } catch (error) {
      finishSpeaking();
      console.error("[NOT TTS]", error);
      emit("error", error.message || "Could not play NOT's voice.");
    }
  }

  function finishSpeaking() {
    isSpeaking = false;
    emit("speaking", false);
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
    currentAudio = null;

    const voiceScreen = document.querySelector('[data-view-panel="voice"]')?.classList.contains("is-active");
    const callOpen = document.querySelector("#call-overlay")?.classList.contains("is-open");
    if (autoContinue && (voiceScreen || callOpen) && onResult) {
      startListening(onResult);
    }
  }

  function interrupt() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
    if (isSpeaking) {
      isSpeaking = false;
      emit("speaking", false);
    }
  }

  return {
    startListening,
    stopListening,
    speak,
    interrupt,
    get isListening() { return isRecording; },
    get isSpeaking() { return isSpeaking; },
  };
})();
