const BRIDGE_URL = "http://127.0.0.1:8765/observe";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "seat-observations") return;

  fetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message.payload),
  })
    .then(async (response) => {
      const data = await response.json().catch(() => ({}));
      sendResponse({ ok: response.ok, status: response.status, data });
    })
    .catch((error) => sendResponse({ ok: false, error: String(error) }));

  return true;
});
