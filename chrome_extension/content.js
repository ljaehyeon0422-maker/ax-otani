const DEFAULTS = {
  enabled: true,
  movieKeyword: "오디세이",
  formatKeyword: "IMAX",
  refreshSeconds: 180,
};

function textOf(el) {
  return (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim();
}

function visible(el) {
  if (!el || !(el instanceof Element)) return false;
  const style = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
}

function parseRemaining(text) {
  let m = text.match(/잔여\s*([0-9]{1,4})\s*석/i);
  if (m) return Number(m[1]);

  m = text.match(/([0-9]{1,4})\s*석\s*(?:남음|잔여)/i);
  if (m) return Number(m[1]);

  m = text.match(/(?:좌석|잔여)[^0-9]{0,12}([0-9]{1,4})\s*\/\s*([0-9]{1,4})/i);
  if (m) return Number(m[1]);

  m = text.match(/([0-9]{1,4})\s*\/\s*([0-9]{1,4})\s*석/i);
  if (m) return Number(m[1]);

  return null;
}

function nearestContext(el) {
  let node = el;
  let best = textOf(el);
  for (let i = 0; i < 5 && node?.parentElement; i++) {
    node = node.parentElement;
    const candidate = textOf(node);
    if (candidate.length >= best.length && candidate.length <= 1600) best = candidate;
    if (/\b\d{1,2}:\d{2}\b/.test(candidate) && candidate.length <= 1600) return candidate;
  }
  return best.slice(0, 1600);
}

function inferTime(context) {
  const m = context.match(/\b([0-2]?\d:[0-5]\d)\b/);
  return m ? m[1].padStart(5, "0") : "";
}

function inferDate(context, body) {
  const all = `${context} ${body}`;
  let m = all.match(/(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})/);
  if (m) return `${m[1]}-${String(m[2]).padStart(2, "0")}-${String(m[3]).padStart(2, "0")}`;
  m = all.match(/\b(\d{1,2})[.\-/](\d{1,2})\b/);
  if (m) {
    const y = new Date().getFullYear();
    return `${y}-${String(m[1]).padStart(2, "0")}-${String(m[2]).padStart(2, "0")}`;
  }
  return "";
}

function hashString(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function collectObservations(settings) {
  const bodyText = textOf(document.body).slice(0, 12000);
  const movieOk = !settings.movieKeyword || bodyText.toLowerCase().includes(settings.movieKeyword.toLowerCase());
  const formatOk = !settings.formatKeyword || bodyText.toLowerCase().includes(settings.formatKeyword.toLowerCase());
  if (!movieOk || !formatOk) return { bodyText, observations: [] };

  const candidates = [];
  const elements = document.querySelectorAll("body *");
  for (const el of elements) {
    if (!visible(el)) continue;
    const own = textOf(el);
    if (!own || own.length > 220) continue;
    const remaining = parseRemaining(own);
    if (remaining === null) continue;
    const context = nearestContext(el);
    const startTime = inferTime(context);
    const watchDate = inferDate(context, bodyText);
    const stableBits = `${settings.movieKeyword}|${watchDate}|${startTime}|${context.replace(/\d+/g, "#").slice(0, 500)}`;
    candidates.push({
      showing_key: hashString(stableBits),
      movie_name: settings.movieKeyword || document.title,
      watch_date: watchDate,
      start_time: startTime,
      remaining,
      context,
    });
  }

  const unique = new Map();
  for (const item of candidates) {
    const existing = unique.get(item.showing_key);
    if (!existing || item.context.length > existing.context.length) unique.set(item.showing_key, item);
  }
  return { bodyText, observations: [...unique.values()].slice(0, 50) };
}

async function sendNow(settings) {
  if (!settings.enabled) return;
  const { bodyText, observations } = collectObservations(settings);
  chrome.runtime.sendMessage({
    type: "seat-observations",
    payload: {
      title: document.title,
      url: location.href,
      page_text: bodyText,
      observations,
    },
  });
}

function scheduleRefresh(settings) {
  if (!settings.enabled) return;
  const seconds = Math.max(120, Number(settings.refreshSeconds) || 180);
  setTimeout(() => {
    if (document.visibilityState === "visible") location.reload();
  }, seconds * 1000);
}

chrome.storage.sync.get(DEFAULTS, (settings) => {
  setTimeout(() => sendNow(settings), 2500);
  scheduleRefresh(settings);

  const observer = new MutationObserver(() => {
    clearTimeout(window.__imaxBridgeTimer);
    window.__imaxBridgeTimer = setTimeout(() => sendNow(settings), 1200);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
});
