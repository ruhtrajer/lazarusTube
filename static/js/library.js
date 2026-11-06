(function () {
  "use strict";

  var HISTORY_KEY = "lazarus.v1.history";
  var FAVORITES_KEY = "lazarus.v1.favorites";

  var libraryEl = document.getElementById("library");
  if (!libraryEl) {
    return;
  }

  var kind = libraryEl.getAttribute("data-kind");
  var key = kind === "favorites" ? FAVORITES_KEY : HISTORY_KEY;
  var grid = document.getElementById("library-grid");
  var countEl = document.getElementById("library-count");
  var emptyEl = document.getElementById("library-empty");
  var clearEl = document.getElementById("clear-library");

  function isArray(value) {
    return Object.prototype.toString.call(value) === "[object Array]";
  }

  function readItems() {
    try {
      if (!window.Lazarus || !window.Lazarus.storage) {
        return [];
      }
      var stored = window.Lazarus.storage.get(key, []);
      return isArray(stored) ? stored : [];
    } catch (storageError) {
      return [];
    }
  }

  function writeItems(items) {
    try {
      if (!window.Lazarus || !window.Lazarus.storage) {
        return false;
      }
      return window.Lazarus.storage.set(key, items);
    } catch (storageError) {
      return false;
    }
  }

  function validItems() {
    var stored = readItems();
    var items = [];
    var i;
    for (i = 0; i < stored.length; i += 1) {
      var item = stored[i];
      if (item && typeof item.id === "string" && item.id) {
        items.push(item);
      }
    }
    return items;
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

  function metaText(item) {
    var parts = [];
    if (item.channel) {
      parts.push(item.channel);
    }
    var views = formatViews(item.view_count);
    if (views) {
      parts.push(views + " vues");
    }
    var duration = formatDuration(item.duration);
    if (duration) {
      parts.push(duration);
    }
    return parts.join(" · ");
  }

  function createCard(item) {
    var itemEl = document.createElement("div");
    itemEl.className = "library-item";

    var card = document.createElement("a");
    card.className = "card";
    card.href = "/watch?v=" + encodeURIComponent(item.id);

    var thumb = document.createElement("div");
    thumb.className = "card-thumb";

    var img = document.createElement("img");
    img.src = "/thumb/" + encodeURIComponent(item.id) + ".jpg?size=mq";
    img.alt = "";
    img.width = 320;
    img.height = 180;
    img.setAttribute("loading", "lazy");
    img.onerror = function () {
      img.style.display = "none";
    };
    thumb.appendChild(img);

    var body = document.createElement("div");
    body.className = "card-body";

    var title = document.createElement("h3");
    title.className = "card-title";
    title.textContent = item.title || item.id;
    body.appendChild(title);

    var meta = document.createElement("p");
    meta.className = "card-meta";
    meta.textContent = metaText(item);
    body.appendChild(meta);

    card.appendChild(thumb);
    card.appendChild(body);

    var remove = document.createElement("button");
    remove.className = "card-remove";
    remove.type = "button";
    remove.textContent = "Retirer";
    remove.onclick = function () {
      removeItem(item.id);
    };

    itemEl.appendChild(card);
    itemEl.appendChild(remove);
    return itemEl;
  }

  function render() {
    if (!grid) {
      return;
    }
    while (grid.firstChild) {
      grid.removeChild(grid.firstChild);
    }

    var items = validItems();
    var i;
    for (i = 0; i < items.length; i += 1) {
      grid.appendChild(createCard(items[i]));
    }

    if (countEl) {
      countEl.textContent = items.length + (items.length > 1 ? " vidéos" : " vidéo");
    }

    if (items.length === 0) {
      if (emptyEl) {
        emptyEl.className = "empty";
      }
      if (clearEl) {
        clearEl.className = "btn btn-secondary hidden";
      }
      return;
    }

    if (emptyEl) {
      emptyEl.className = "empty hidden";
    }
    if (clearEl) {
      clearEl.className = "btn btn-secondary";
    }
  }

  function removeItem(id) {
    var items = validItems();
    var next = [];
    var i;
    for (i = 0; i < items.length; i += 1) {
      if (items[i].id !== id) {
        next.push(items[i]);
      }
    }
    writeItems(next);
    render();
  }

  function clearLibrary() {
    var message = kind === "favorites" ? "Vider tous les favoris ?" : "Vider tout l'historique ?";
    var confirmed = false;
    try {
      confirmed = window.confirm(message);
    } catch (confirmError) {
      confirmed = false;
    }
    if (!confirmed) {
      return;
    }
    writeItems([]);
    render();
  }

  if (clearEl) {
    clearEl.onclick = clearLibrary;
  }

  render();
})();
