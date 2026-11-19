document.addEventListener("DOMContentLoaded", () => {
  window.sendChatToBackend = function (text, language = "en") {
    if (!text.trim()) return;
    if (window.notSocket) {
      window.notSocket.send(text, language);
    }
  };

  const homeMic = document.getElementById("home-mic");
  if (homeMic) {
    homeMic.addEventListener("click", () => {
      if (window.NOTAudio.isListening) window.NOTAudio.stopListening();
      else
        window.NOTAudio.startListening((text) =>
          window.sendChatToBackend(text),
        );
    });
  }

  window.addEventListener("not:camera_request", async (ev) => {
    const prompt = ev.detail.prompt || "Describe what is visible.";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();
      await new Promise((r) => setTimeout(r, 1000));
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0);
      const imageBase64 = canvas.toDataURL("image/jpeg", 0.85);
      stream.getTracks().forEach((t) => t.stop());
      const resp = await fetch("/api/vision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_base64: imageBase64, prompt }),
      });
      const data = await resp.json();
      if (data.text && window.NOTAudio) window.NOTAudio.speak(data.text);
    } catch (err) {
      console.error("[Bridge] Camera error:", err);
    }
  });
});
