window.NOTAudio = (function () {
  let mediaRecorder = null,
    audioChunks = [],
    isRecording = false,
    onResult = null,
    stream = null;
  let currentAudio = null;
  let audioContext = null,
    analyser = null,
    dataArray = null;
  let isSpeaking = false;

  async function initAudioContext() {
    if (audioContext) return;
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    dataArray = new Uint8Array(analyser.frequencyBinCount);
  }

  async function startListening(callback) {
    if (isRecording) return;
    onResult = callback;
    await initAudioContext();
    if (audioContext.state === "suspended") await audioContext.resume();

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
    } catch (err) {
      alert("Mic permission denied");
      return;
    }

    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "voice.webm");

      const lang = localStorage.getItem("not-lang") || "en";
      try {
        const resp = await fetch(`/api/transcribe?language=${lang}`, {
          method: "POST",
          body: formData,
        });
        const data = await resp.json();
        if (data.text && onResult) onResult(data.text);
      } catch (err) {
        console.error("[STT] Error:", err);
      }
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };

    isRecording = true;
    mediaRecorder.start();
    window.dispatchEvent(new CustomEvent("not:listening", { detail: true }));
    monitorSilenceForAutoStop();
  }

  function monitorSilenceForAutoStop() {
    if (!analyser || !isRecording) return;
    analyser.getByteFrequencyData(dataArray);
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
    let average = sum / dataArray.length;

    if (average > 10) {
      window._lastVoiceTime = Date.now();
    } else {
      if (window._lastVoiceTime && Date.now() - window._lastVoiceTime > 800) {
        stopListening();
        return;
      }
    }
    if (isRecording) requestAnimationFrame(monitorSilenceForAutoStop);
  }

  function stopListening() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;
      window.dispatchEvent(new CustomEvent("not:listening", { detail: false }));
      window._lastVoiceTime = null;
    }
  }

  function speak(text, voiceProfile = "nova") {
    if (!text) return;
    isSpeaking = true;
    window.dispatchEvent(new CustomEvent("not:speaking", { detail: true }));
    const url = `/api/tts?text=${encodeURIComponent(text)}&voice=${voiceProfile}`;
    if (currentAudio) currentAudio.pause();
    currentAudio = new Audio(url);

    currentAudio.onplay = () => {
      startInterruptionMonitor();
    };
    currentAudio.onended = () => {
      isSpeaking = false;
      window.dispatchEvent(new CustomEvent("not:speaking", { detail: false }));

      const isVoiceScreen = document
        .querySelector('[data-view-panel="voice"]')
        ?.classList.contains("is-active");
      const isCallOpen = document
        .querySelector("#call-overlay")
        ?.classList.contains("is-open");

      if ((isVoiceScreen || isCallOpen) && !isRecording) {
        setTimeout(() => {
          window.NOTAudio.startListening((res) => {
            if (window.sendChatToBackend) window.sendChatToBackend(res);
          });
        }, 250);
      }
    };
    currentAudio
      .play()
      .catch((e) => console.warn("[TTS] Autoplay blocked:", e));
  }

  function startInterruptionMonitor() {
    if (!analyser) return;
    const checkInterruption = () => {
      if (!isSpeaking) return;
      analyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
      let average = sum / dataArray.length;

      if (average > 22) {
        interrupt();
        window.NOTAudio.startListening((res) => {
          if (window.sendChatToBackend) window.sendChatToBackend(res);
        });
        return;
      }
      requestAnimationFrame(checkInterruption);
    };
    requestAnimationFrame(checkInterruption);
  }

  function interrupt() {
    isSpeaking = false;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    window.dispatchEvent(new CustomEvent("not:speaking", { detail: false }));
  }

  return {
    startListening,
    stopListening,
    speak,
    interrupt,
    get isListening() {
      return isRecording;
    },
  };
})();
