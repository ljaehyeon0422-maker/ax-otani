const DEFAULTS = {
  enabled: true,
  movieKeyword: "오디세이",
  formatKeyword: "IMAX",
  refreshSeconds: 180,
};

const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(DEFAULTS, (settings) => {
  $("enabled").checked = Boolean(settings.enabled);
  $("movieKeyword").value = settings.movieKeyword || "";
  $("formatKeyword").value = settings.formatKeyword || "";
  $("refreshSeconds").value = Math.max(120, Number(settings.refreshSeconds) || 180);
});

$("save").addEventListener("click", () => {
  const settings = {
    enabled: $("enabled").checked,
    movieKeyword: $("movieKeyword").value.trim(),
    formatKeyword: $("formatKeyword").value.trim(),
    refreshSeconds: Math.max(120, Number($("refreshSeconds").value) || 180),
  };
  chrome.storage.sync.set(settings, () => {
    $("status").textContent = "✅ 저장했습니다. CGV 탭을 한 번 새로고침하세요.";
  });
});
