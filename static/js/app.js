(function () {
  "use strict";

  function xhr(method, url, done) {
    var req;
    var finished = false;

    function finish(status, data, text) {
      if (finished) {
        return;
      }
      finished = true;
      if (typeof done === "function") {
        done(status, data, text);
      }
    }

    try {
      req = new XMLHttpRequest();
      req.open(method, url, true);
    } catch (openError) {
      finish(0, null, "");
      return;
    }

    req.onreadystatechange = function () {
      if (req.readyState !== 4) {
        return;
      }
      var text = req.responseText || "";
      var data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (parseError) {
        data = null;
      }
      finish(req.status, data, text);
    };

    try {
      req.send();
    } catch (sendError) {
      finish(0, null, "");
    }
  }

  function pad(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function formatTime(value) {
    var total = parseInt(value, 10);
    if (isNaN(total) || total < 0) {
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

  function storageGet(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      if (raw === null) {
        return fallback;
      }
      return JSON.parse(raw);
    } catch (storageError) {
      return fallback;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (storageError) {
      return false;
    }
  }

  function storageRemove(key) {
    try {
      window.localStorage.removeItem(key);
      return true;
    } catch (storageError) {
      return false;
    }
  }

  window.Lazarus = {
    xhr: xhr,
    formatTime: formatTime,
    storage: {
      get: storageGet,
      set: storageSet,
      remove: storageRemove
    }
  };
})();
