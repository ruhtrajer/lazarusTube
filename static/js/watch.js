(function () {
  "use strict";

  var id = document.body.getAttribute("data-video-id");
  var player = document.getElementById("player");
  var overlay = document.getElementById("prepare-overlay");
  var progressFill = document.getElementById("progress-fill");
  var progressLabel = document.getElementById("progress-label");
  var prepareText = document.getElementById("prepare-text");
  var errorBox = document.getElementById("error-box");
  var errorText = document.getElementById("error-text");
  var retryEl = document.getElementById("retry");
  var titleEl = document.getElementById("video-title");
  var metaEl = document.getElementById("video-meta");
  var timer = null;

  function stopPolling() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function pad(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function formatDuration(value) {
    var total = parseInt(value, 10);
    if (isNaN(total) || total <= 0) {
      return "";
    }
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var seconds = total % 60;
    if (hours > 0) {
      return hours + ":" + pad(minutes) + ":" + pad(seconds);
    }
    return minutes + ":" + pad(seconds);
  }

  function compactNumber(value) {
    var text = value.toFixed(1);
    if (text.slice(-2) === ".0") {
      text = text.slice(0, -2);
    }
    return text.replace(".", ",");
  }

  function formatViews(count) {
    var views = parseInt(count, 10);
    if (isNaN(views) || views < 0) {
      return "";
    }
    if (views >= 1000000) {
      return compactNumber(views / 1000000) + " M";
    }
    if (views >= 1000) {
      return compactNumber(views / 1000) + " k";
    }
    return String(views);
  }

  function updateMeta(meta) {
    if (!meta) {
      return;
    }
    if (meta.title && titleEl) {
      titleEl.textContent = meta.title;
    }
    if (!metaEl) {
      return;
    }
    var parts = [];
    if (meta.channel) {
      parts.push(meta.channel);
    }
    var views = formatViews(meta.view_count);
    if (views) {
      parts.push(views + " vues");
    }
    var duration = formatDuration(meta.duration);
    if (duration) {
      parts.push(duration);
    }
    if (parts.length) {
      metaEl.textContent = parts.join(" · ");
    }
  }

  function setProgress(progress) {
    var value = typeof progress === "number" ? progress : -1;
    if (isNaN(value) || value < 0) {
      if (progressFill) {
        progressFill.style.width = "0%";
      }
      if (progressLabel) {
        progressLabel.textContent = "0 %";
      }
      if (prepareText) {
        prepareText.textContent = "Préparation…";
      }
      return;
    }
    if (value > 100) {
      value = 100;
    }
    var rounded = Math.round(value);
    if (progressFill) {
      progressFill.style.width = rounded + "%";
    }
    if (progressLabel) {
      progressLabel.textContent = rounded + " %";
    }
    if (prepareText) {
      prepareText.textContent = "Préparation de la vidéo…";
    }
  }

  function showError(message) {
    stopPolling();
    if (overlay) {
      overlay.className = "hidden";
    }
    if (errorText) {
      errorText.textContent = message || "Impossible de préparer cette vidéo.";
    }
    if (errorBox) {
      errorBox.className = "";
    }
  }

  function setReady() {
    stopPolling();
    if (overlay) {
      overlay.className = "hidden";
    }
    if (errorBox) {
      errorBox.className = "hidden";
    }
    if (player) {
      player.src = "/stream?v=" + encodeURIComponent(id);
    }
  }

  function poll() {
    window.Lazarus.xhr(
      "GET",
      "/api/status?v=" + encodeURIComponent(id),
      function (status, snap) {
        if (status >= 400) {
          showError((snap && snap.error) || "Impossible de vérifier la préparation.");
          return;
        }
        if (!snap) {
          return;
        }
        updateMeta(snap.meta);
        if (snap.state === "ready") {
          setReady();
          return;
        }
        if (snap.state === "error") {
          showError(snap.error || "Impossible de préparer cette vidéo.");
          return;
        }
        if (snap.state === "downloading") {
          setProgress(snap.progress);
        } else {
          setProgress(-1);
        }
      }
    );
  }

  function startPolling() {
    if (timer !== null) {
      return;
    }
    timer = window.setInterval(poll, 1500);
    poll();
  }

  function prepare(retry) {
    stopPolling();
    if (errorBox) {
      errorBox.className = "hidden";
    }
    if (overlay) {
      overlay.className = "";
    }
    setProgress(0);

    var url = "/api/prepare?v=" + encodeURIComponent(id);
    if (retry) {
      url += "&retry=1";
    }

    window.Lazarus.xhr("POST", url, function (status, snap) {
      if (status >= 400) {
        showError((snap && snap.error) || "Impossible de préparer cette vidéo.");
        return;
      }
      if (!snap) {
        startPolling();
        return;
      }
      updateMeta(snap.meta);
      if (snap.state === "ready") {
        setReady();
      } else if (snap.state === "error") {
        showError(snap.error || "Impossible de préparer cette vidéo.");
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

  if (window.addEventListener) {
    window.addEventListener("pagehide", stopPolling);
  }

  if (id && window.Lazarus) {
    prepare(false);
  }
})();
