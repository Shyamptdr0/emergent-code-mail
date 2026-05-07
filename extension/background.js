// MailTrack background service worker — polls for new opens, shows desktop notifications
// AND broadcasts "open" events to all Gmail tabs for in-page toast UI.

const POLL_ALARM = "mt-poll";
let lastSeen = {}; // id -> open_count

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.17 }); // every ~10 seconds
  chrome.storage.local.get(["lastSeen"], (v) => { lastSeen = v.lastSeen || {}; });
});

chrome.runtime.onStartup?.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.17 });
  chrome.storage.local.get(["lastSeen"], (v) => { lastSeen = v.lastSeen || {}; });
});

chrome.alarms.onAlarm.addListener((a) => { if (a.name === POLL_ALARM) poll(); });

// Also run poll immediately when service worker starts
poll();

async function broadcastToGmailTabs(payload) {
  chrome.tabs.query({ url: "https://mail.google.com/*" }, (tabs) => {
    tabs.forEach((t) => {
      try { chrome.tabs.sendMessage(t.id, payload, () => void chrome.runtime.lastError); } catch (e) {}
    });
  });
}

async function poll() {
  const cfg = await new Promise((res) =>
    chrome.storage.sync.get(["backend_url", "ext_api_key"], (v) => res(v))
  );
  if (!cfg.backend_url || !cfg.ext_api_key) return;

  try {
    const r = await fetch(cfg.backend_url + "/api/emails/by-ext", {
      headers: { "X-Ext-Key": cfg.ext_api_key },
    });
    if (!r.ok) return;
    const list = await r.json();

    list.forEach((e) => {
      const prev = lastSeen[e.id];
      if (typeof prev === "undefined") {
        lastSeen[e.id] = e.open_count;
        return;
      }
      if (e.open_count > prev) {
        const newlyOpened = e.open_count - prev;
        try {
          chrome.notifications.create("mt-" + e.id + "-" + Date.now(), {
            type: "basic",
            iconUrl: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
            title: "Just opened mail",
            message: `${e.recipient}\nSubject: ${e.subject || "(no subject)"}${newlyOpened > 1 ? "\nOpened " + newlyOpened + "× just now" : ""}`,
            contextMessage: newlyOpened > 1 ? `Opened ${newlyOpened} times` : "Opened just now",
            priority: 2,
            requireInteraction: false,
            silent: false,
          });
        } catch (err) { console.warn("notification failed", err); }
        lastSeen[e.id] = e.open_count;
      }
    });
    chrome.storage.local.set({ lastSeen });

    // Due follow-ups notification
    const fr = await fetch(cfg.backend_url + "/api/follow-ups/due", {
      headers: { "X-Ext-Key": cfg.ext_api_key },
    });
    if (fr.ok) {
      const dues = await fr.json();
      for (const f of dues) {
        chrome.notifications.create("mtfu-" + f.id, {
          type: "basic",
          iconUrl: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
          title: (f.mode === "auto" ? "Auto follow-up due: " : "Follow-up reminder: ") + f.recipient,
          message: f.subject,
          priority: 1,
        });
      }
    }
  } catch (e) { console.warn("MailTrack poll error", e); }
}

chrome.notifications.onClicked.addListener(() => {
  chrome.tabs.create({ url: "https://mail.google.com/" });
});
