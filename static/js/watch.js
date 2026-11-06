(function () {
  "use strict";

  var body = document.body;
  var videoId = body ? body.getAttribute("data-video-id") : "";
  var player = document.getElementById("player");
  var statusEl = document.getElementById("status");
  var retryEl = document.getElementById("retry");
  var timer = null;

  function setStatus(message) {
    if (statusEl) {
      statusEl.textContent = message || "";
    }
  }

  function stopPolling() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function showError(message) {
    stopPolling();
    setStatus(message || "Impossible de préparer cette vidéo.");
    if (retryEl) {
      retryEl.style.display = "inline-block";
    }
  }

  function setReady() {
    stopPolling();
    setStatus("");
    if (player && player.src.indexOf("/stream?") === -1) {
      player.src = "/stream?v=" + encodeURIComponent(videoId);
    }
  }

  function poll() {
    window.Lazarus.xhr(
      "GET",
      "/api/status?v=" + encodeURIComponent(videoId),
      function (status, data) {
        if (status >= 400) {
          showError((data && data.error) || "Impossible de vérifier la préparation.");
          return;
        }
        if (!data) {
          return;
        }
        if (data.state === "ready") {
          setReady();
          return;
        }
        if (data.state === "error") {
          showError(data.error || "Impossible de préparer cette vidéo.");
          return;
        }
        if (data.state === "downloading") {
          if (typeof data.progress === "number" && data.progress >= 0) {
            setStatus("Préparation de la vidéo… " + Math.round(data.progress) + " %");
          } else {
            setStatus("Préparation de la vidéo…");
          }
        } else {
          setStatus("Vidéo en file d'attente…");
        }
      }
    );
  }

  function startPolling() {
    if (timer === null) {
      timer = setInterval(poll, 1500);
    }
  }

  function prepare(retry) {
    if (retryEl) {
      retryEl.style.display = "none";
    }
    setStatus("Préparation de la vidéo…");

    var url = "/api/prepare?v=" + encodeURIComponent(videoId);
    if (retry) {
      url += "&retry=1";
    }

    window.Lazarus.xhr("POST", url, function (status, data) {
      if (status >= 400) {
        showError((data && data.error) || "Impossible de préparer cette vidéo.");
        return;
      }
      if (!data) {
        startPolling();
        return;
      }
      if (data.state === "ready") {
        setReady();
      } else if (data.state === "error") {
        showError(data.error || "Impossible de préparer cette vidéo.");
      } else {
        startPolling();
      }
    });
  }

  if (retryEl) {
    retryEl.onclick = function () {
      prepare(true);
    };
  }

  if (videoId && window.Lazarus) {
    prepare(false);
  }
})();
