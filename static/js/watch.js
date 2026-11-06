(function () {
  "use strict";

  var RESUME_KEY = "lazarus.v1.resume";
  var HISTORY_KEY = "lazarus.v1.history";
  var FAVORITES_KEY = "lazarus.v1.favorites";
  var MAX_RESUME = 50;
  var MAX_HISTORY = 50;
  var MAX_FAVORITES = 200;
  var RESUME_INTERVAL_MS = 5000;

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
  var favoriteEl = document.getElementById("favorite");
  var backEl = document.getElementById("back-10");
  var forwardEl = document.getElementById("forward-10");
  var fullscreenEl = document.getElementById("fullscreen");
  var resumeBar = document.getElementById("resume-bar");
  var resumeTimeEl = document.getElementById("resume-time");
  var resumeYes = document.getElementById("resume-yes");
  var resumeNo = document.getElementById("resume-no");
  var timer = null;
  var lastResumeSave = 0;
  var historyAdded = false;
  var resumeAt = 0;
  var errorRetried = false;
  var resumeOffer = null;

  function now() {
    return (new Date()).getTime();
  }

  function isArray(value) {
    return Object.prototype.toString.call(value) === "[object Array]";
  }

  function storageGet(key, fallback) {
    if (!window.Lazarus || !window.Lazarus.storage) {
      return fallback;
    }
    return window.Lazarus.storage.get(key, fallback);
  }

  function storageSet(key, value) {
    if (!window.Lazarus || !window.Lazarus.storage) {
      return false;
    }
    return window.Lazarus.storage.set(key, value);
  }

  function dataValue(name) {
    var value = document.body.getAttribute(name);
    return value === null ? "" : value;
  }

  function setDataValue(name, value) {
    try {
      document.body.setAttribute(name, value === null || typeof value === "undefined" ? "" : String(value));
    } catch (attrError) {
      return;
    }
  }

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

  function formatTime(value) {
    if (window.Lazarus && typeof window.Lazarus.formatTime === "function") {
      return window.Lazarus.formatTime(value);
    }
    return formatDuration(value);
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

  function mediaDuration() {
    var value = player ? player.duration : NaN;
    if (typeof value === "number" && isFinite(value) && value > 0) {
      return value;
    }
    var fallback = parseInt(dataValue("data-duration"), 10);
    if (!isNaN(fallback) && fallback > 0) {
      return fallback;
    }
    return 0;
  }

  function videoEntry() {
    var duration = parseInt(dataValue("data-duration"), 10);
    var views = parseInt(dataValue("data-view-count"), 10);
    return {
      id: id,
      title: dataValue("data-title"),
      channel: dataValue("data-channel"),
      duration: isNaN(duration) ? 0 : duration,
      view_count: isNaN(views) ? 0 : views,
      ts: now()
    };
  }

  function readList(key) {
    var stored = storageGet(key, []);
    if (!isArray(stored)) {
      return [];
    }
    return stored;
  }

  function updateMeta(meta) {
    if (!meta) {
      return;
    }
    if (meta.title) {
      if (titleEl) {
        titleEl.textContent = meta.title;
      }
      setDataValue("data-title", meta.title);
    }
    if (meta.channel) {
      setDataValue("data-channel", meta.channel);
    }
    if (meta.duration !== null && typeof meta.duration !== "undefined") {
      setDataValue("data-duration", meta.duration);
    }
    if (meta.view_count !== null && typeof meta.view_count !== "undefined") {
      setDataValue("data-view-count", meta.view_count);
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

  function readResumeMap() {
    var stored = storageGet(RESUME_KEY, {});
    if (!stored || typeof stored !== "object" || isArray(stored)) {
      return {};
    }
    return stored;
  }

  function pruneResumeMap(map) {
    var keys = [];
    var key;
    for (key in map) {
      if (Object.prototype.hasOwnProperty.call(map, key)) {
        keys.push(key);
      }
    }
    if (keys.length <= MAX_RESUME) {
      return map;
    }
    keys.sort(function (a, b) {
      var ta = map[a] && typeof map[a].ts === "number" ? map[a].ts : 0;
      var tb = map[b] && typeof map[b].ts === "number" ? map[b].ts : 0;
      return tb - ta;
    });
    var pruned = {};
    var i;
    for (i = 0; i < MAX_RESUME; i += 1) {
      pruned[keys[i]] = map[keys[i]];
    }
    return pruned;
  }

  function saveResume(seconds, duration) {
    var map = readResumeMap();
    map[id] = {
      t: Math.floor(seconds),
      d: Math.floor(duration),
      ts: now()
    };
    storageSet(RESUME_KEY, pruneResumeMap(map));
  }

  function clearResume() {
    var map = readResumeMap();
    if (map[id]) {
      delete map[id];
      storageSet(RESUME_KEY, map);
    }
  }

  function storedResume() {
    var entry = readResumeMap()[id];
    if (!entry) {
      return null;
    }
    var seconds = parseInt(entry.t, 10);
    if (isNaN(seconds) || seconds <= 0) {
      return null;
    }
    return seconds;
  }

  function showResumeBar(seconds) {
    if (!resumeBar) {
      return;
    }
    if (resumeTimeEl) {
      resumeTimeEl.textContent = formatTime(seconds);
    }
    resumeBar.className = "";
  }

  function hideResumeBar() {
    if (resumeBar) {
      resumeBar.className = "hidden";
    }
  }

  function onTimeUpdate() {
    if (!player) {
      return;
    }
    var current = player.currentTime;
    var duration = mediaDuration();
    if (!(current > 5) || !(duration > 0) || !(current < duration - 10)) {
      return;
    }
    var stamp = now();
    if (stamp - lastResumeSave < RESUME_INTERVAL_MS) {
      return;
    }
    lastResumeSave = stamp;
    saveResume(current, duration);
  }

  function onLoadedMetadata() {
    if (!player) {
      return;
    }
    errorRetried = false;
    if (resumeAt > 0) {
      try {
        player.currentTime = resumeAt;
      } catch (seekError) {
        resumeAt = 0;
      }
      resumeAt = 0;
      return;
    }
    var seconds = storedResume();
    if (seconds !== null) {
      resumeOffer = seconds;
      showResumeBar(seconds);
    }
  }

  function onEnded() {
    resumeOffer = null;
    hideResumeBar();
    clearResume();
  }

  function onResumeYes() {
    var seconds = resumeOffer;
    if (seconds === null) {
      seconds = storedResume();
    }
    if (player && seconds !== null) {
      try {
        player.currentTime = seconds;
      } catch (seekError) {
        return;
      }
      lastResumeSave = now();
    }
    resumeOffer = null;
    hideResumeBar();
  }

  function onResumeNo() {
    resumeOffer = null;
    hideResumeBar();
    clearResume();
  }

  function isFavorite() {
    var items = readList(FAVORITES_KEY);
    var i;
    for (i = 0; i < items.length; i += 1) {
      if (items[i] && items[i].id === id) {
        return true;
      }
    }
    return false;
  }

  function setFavoriteState(active) {
    if (!favoriteEl) {
      return;
    }
    favoriteEl.setAttribute("aria-pressed", active ? "true" : "false");
    favoriteEl.textContent = active ? "♥ Favori" : "♡ Favori";
  }

  function toggleFavorite() {
    var items = readList(FAVORITES_KEY);
    var next = [];
    var seen = {};
    var wasFavorite = false;
    var i;
    for (i = 0; i < items.length; i += 1) {
      if (items[i] && items[i].id === id) {
        wasFavorite = true;
      }
    }
    if (!wasFavorite) {
      next.push(videoEntry());
      seen[id] = true;
    }
    for (i = 0; i < items.length; i += 1) {
      var item = items[i];
      if (!item || item.id === id || typeof item.id !== "string" || seen[item.id]) {
        continue;
      }
      seen[item.id] = true;
      next.push(item);
    }
    if (next.length > MAX_FAVORITES) {
      next = next.slice(0, MAX_FAVORITES);
    }
    storageSet(FAVORITES_KEY, next);
    setFavoriteState(!wasFavorite);
  }

  function addHistory() {
    var items = readList(HISTORY_KEY);
    var next = [videoEntry()];
    var seen = {};
    var i;
    seen[id] = true;
    for (i = 0; i < items.length; i += 1) {
      var item = items[i];
      if (!item || typeof item.id !== "string" || seen[item.id]) {
        continue;
      }
      seen[item.id] = true;
      next.push(item);
    }
    if (next.length > MAX_HISTORY) {
      next = next.slice(0, MAX_HISTORY);
    }
    storageSet(HISTORY_KEY, next);
  }

  function onPlay() {
    if (historyAdded) {
      return;
    }
    historyAdded = true;
    addHistory();
  }

  function onBack10() {
    if (!player) {
      return;
    }
    try {
      player.currentTime = Math.max(0, player.currentTime - 10);
    } catch (seekError) {
      return;
    }
  }

  function onForward10() {
    if (!player) {
      return;
    }
    var duration = mediaDuration();
    if (duration <= 0) {
      duration = player.duration;
    }
    var target = player.currentTime + 10;
    if (typeof duration === "number" && isFinite(duration) && duration > 0 && target > duration) {
      target = duration;
    }
    try {
      player.currentTime = target;
    } catch (seekError) {
      return;
    }
  }

  function onFullscreen() {
    if (!player) {
      return;
    }
    try {
      if (player.webkitEnterFullscreen) {
        player.webkitEnterFullscreen();
      } else if (player.requestFullscreen) {
        player.requestFullscreen();
      }
    } catch (fullscreenError) {
      return;
    }
  }

  function onPlayerError() {
    if (!player || errorRetried) {
      return;
    }
    errorRetried = true;
    try {
      resumeAt = player.currentTime > 0 ? player.currentTime : 0;
    } catch (timeError) {
      resumeAt = 0;
    }
    prepare(false);
  }

  if (favoriteEl) {
    setFavoriteState(isFavorite());
    favoriteEl.onclick = toggleFavorite;
  }
  if (backEl) {
    backEl.onclick = onBack10;
  }
  if (forwardEl) {
    forwardEl.onclick = onForward10;
  }
  if (fullscreenEl) {
    fullscreenEl.onclick = onFullscreen;
  }
  if (resumeYes) {
    resumeYes.onclick = onResumeYes;
  }
  if (resumeNo) {
    resumeNo.onclick = onResumeNo;
  }

  if (retryEl) {
    retryEl.onclick = function () {
      prepare(true);
    };
  }

  if (player && player.addEventListener) {
    player.addEventListener("timeupdate", onTimeUpdate);
    player.addEventListener("loadedmetadata", onLoadedMetadata);
    player.addEventListener("play", onPlay);
    player.addEventListener("ended", onEnded);
    player.addEventListener("error", onPlayerError);
  }

  if (window.addEventListener) {
    window.addEventListener("pagehide", stopPolling);
  }

  if (id && window.Lazarus) {
    prepare(false);
  }
})();
