(function () {
  "use strict";

  var SEARCHES_KEY = "lazarus.v1.searches";
  var MAX_SEARCHES = 8;

  function trim(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/^\s+/, "")
      .replace(/\s+$/, "");
  }

  function getSearches() {
    if (!window.Lazarus || !window.Lazarus.storage) {
      return [];
    }
    var stored = window.Lazarus.storage.get(SEARCHES_KEY, []);
    if (!stored || typeof stored.length !== "number") {
      return [];
    }
    var searches = [];
    var i;
    for (i = 0; i < stored.length && searches.length < MAX_SEARCHES; i += 1) {
      if (typeof stored[i] === "string" && trim(stored[i])) {
        searches.push(trim(stored[i]));
      }
    }
    return searches;
  }

  function saveSearches(searches) {
    if (!window.Lazarus || !window.Lazarus.storage) {
      return;
    }
    window.Lazarus.storage.set(SEARCHES_KEY, searches.slice(0, MAX_SEARCHES));
  }

  function addSearch(value) {
    var query = trim(value);
    if (!query) {
      return;
    }
    var previous = getSearches();
    var searches = [query];
    var i;
    for (i = 0; i < previous.length; i += 1) {
      if (previous[i] !== query) {
        searches.push(previous[i]);
      }
    }
    saveSearches(searches);
  }

  function clearRecent(container) {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
  }

  function renderRecent() {
    var container = document.getElementById("recent-searches");
    var input = document.getElementById("search-input");
    if (!container) {
      return;
    }

    clearRecent(container);

    // Sur une page de résultats le champ est déjà rempli : on n'affiche pas
    // les chips. Elles ne servent qu'à l'état initial, champ vide.
    if (input && trim(input.value)) {
      return;
    }

    var searches = getSearches();
    if (!searches.length) {
      return;
    }

    var label = document.createElement("span");
    label.className = "recent-label";
    label.textContent = "Récents :";
    container.appendChild(label);

    var i;
    for (i = 0; i < searches.length; i += 1) {
      var chip = document.createElement("a");
      chip.className = "chip";
      chip.href = "/search?q=" + encodeURIComponent(searches[i]);
      chip.textContent = searches[i];
      container.appendChild(chip);
    }
  }

  function setLoading(form) {
    var button = document.getElementById("search-submit");
    var label = document.getElementById("search-submit-label");
    var spinner = document.getElementById("search-spinner");
    var input = document.getElementById("search-input");

    if (input) {
      addSearch(input.value);
    }

    if (button) {
      button.disabled = true;
      if (label) {
        label.textContent = "Recherche…";
      } else {
        button.textContent = "Recherche…";
      }
    }

    if (spinner) {
      spinner.className = "spinner";
    }

    if (form) {
      form.setAttribute("aria-busy", "true");
    }
  }

  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  var form = document.getElementById("search-form");
  if (form && form.addEventListener) {
    form.addEventListener("submit", function () {
      setLoading(form);
    });
  }

  ready(renderRecent);
})();
