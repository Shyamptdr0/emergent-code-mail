// MailTrack content script v0.3.1 — injects tracking pixel when compose opens
(function () {
  const STATE = { config: null, sentMap: {}, composeMap: new WeakMap(), dead: false };
  const log = (...a) => console.log("[MailTrack]", ...a);

  function isContextAlive() {
    try {
      // Accessing chrome.runtime.id throws when context is invalidated
      return !!(chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  }

  async function getConfig() {
    if (!isContextAlive()) { STATE.dead = true; return {}; }
    return new Promise((res) => {
      try {
        chrome.storage.sync.get(["backend_url", "ext_api_key"], (v) => {
          if (chrome.runtime.lastError) { STATE.dead = true; res({}); return; }
          res(v || {});
        });
      } catch (e) {
        STATE.dead = true;
        res({});
      }
    });
  }

  async function api(path, opts = {}) {
    const cfg = STATE.config;
    if (!cfg?.backend_url || !cfg?.ext_api_key) throw new Error("not_configured");
    const r = await fetch(cfg.backend_url + path, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        "X-Ext-Key": cfg.ext_api_key,
        ...(opts.headers || {}),
      },
    });
    if (!r.ok) throw new Error("api_error_" + r.status);
    return r.json();
  }

  // ---------- Compose helpers ----------
  function findSendButton(dlg) {
    return (
      dlg.querySelector('div[role="button"][data-tooltip*="Send"]') ||
      dlg.querySelector('div[role="button"][aria-label*="Send"]') ||
      dlg.querySelector('div.T-I.J-J5-Ji.aoO') ||
      dlg.querySelector('div[command="Send"]')
    );
  }
  function findTo(dlg) {
    const chip = dlg.querySelector("[email]");
    if (chip) return chip.getAttribute("email");
    const f = dlg.querySelector('textarea[name="to"], input[name="to"]');
    return ((f?.value || f?.textContent || "").split(",")[0] || "").trim();
  }
  function findSubject(dlg) {
    return dlg.querySelector('input[name="subjectbox"]')?.value || "";
  }
  function findBody(dlg) {
    return dlg.querySelector('div[g_editable="true"], div[contenteditable="true"][role="textbox"]');
  }

  // ---------- Create tracking + inject pixel immediately when compose opens ----------
  async function ensureTrackingForCompose(dlg) {
    if (STATE.composeMap.has(dlg)) return STATE.composeMap.get(dlg).tid;
    
    // Mark as pending to avoid parallel calls
    STATE.composeMap.set(dlg, { pending: true });

    try {
      log("creating tracking for compose...");
      const res = await api("/api/track/create", {
        method: "POST",
        body: JSON.stringify({
          recipient: "pending@unknown",
          subject: "(draft)",
          message_preview: "",
        }),
      });

      log("tracking created, storing state", res.id);
      STATE.composeMap.set(dlg, { tid: res.id, pixel_url: res.pixel_url });
      return res.id;
    } catch (e) {
      console.error("[MailTrack] create failed", e);
      STATE.composeMap.delete(dlg);
      return null;
    }
  }

  async function attachToCompose() {
    const composes = document.querySelectorAll('div[role="dialog"]');
    for (const dlg of composes) {
      // If the dialog is hidden (closed/sent), clean up our state so it doesn't leak into the next email
      if (dlg.offsetParent === null) {
        STATE.composeMap.delete(dlg);
        delete dlg.dataset.mtAttached;
        continue;
      }

      if (dlg.dataset.mtAttached) continue;
      const sendBtn = findSendButton(dlg);
      if (!sendBtn || !findBody(dlg)) continue;
      dlg.dataset.mtAttached = "1";

      // Add visual badge next to Send button
      if (!sendBtn.parentElement.querySelector(".mt-badge")) {
        const badge = document.createElement("span");
        badge.className = "mt-badge";
        badge.title = "MailTrack — tracking enabled";
        badge.textContent = "✓✓ tracked";
        sendBtn.parentElement.appendChild(badge);
      }

      // Inject pixel NOW (not on send)
      ensureTrackingForCompose(dlg);

      // On send, update tracking with real recipient/subject (fire-and-forget)
      const updateOnSend = () => {
        const info = STATE.composeMap.get(dlg);
        if (!info?.tid) return;
        
        const body = findBody(dlg);
        const recipient = findTo(dlg) || "unknown";
        const subject = findSubject(dlg) || "(no subject)";
        const preview = (body?.innerText || "").slice(0, 140);
        api(`/api/track/update/${info.tid}`, {
          method: "POST",
          body: JSON.stringify({ recipient, subject, message_preview: preview }),
        }).then(() => log("tracking updated on send", info.tid, recipient, subject))
          .catch((e) => console.warn("[MailTrack] update failed", e));
          
        // CRITICAL FIX: Clear state immediately on send so reused dialogs get a fresh ID
        STATE.composeMap.delete(dlg);
        delete dlg.dataset.mtAttached;
      };
      
      // Use delegated listener on the dialog to survive Gmail replacing the Send button DOM
      dlg.addEventListener("click", (ev) => {
        const btn = findSendButton(dlg);
        if (btn && (ev.target === btn || btn.contains(ev.target))) {
          updateOnSend();
        }
      }, true);
      
      dlg.addEventListener("keydown", (ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") updateOnSend();
      }, true);
    }
    enforcePixels();
  }

  function enforcePixels() {
    document.querySelectorAll('div[role="dialog"]').forEach(dlg => {
      const info = STATE.composeMap.get(dlg);
      if (info && info.tid) {
        const body = findBody(dlg);
        if (body) {
          // 1. Aggressively strip any pixel that doesn't match our current TID
          const imgs = body.querySelectorAll("img");
          imgs.forEach(img => {
            const src = img.src || "";
            const style = (img.getAttribute("style") || "").replace(/\s/g, "").toLowerCase();
            
            // CRITICAL FIX: Google Image Proxy completely hides the original URL in quoted replies.
            // To guarantee old pixels are removed, we delete ANY 1x1 image or any image with left:-9999px
            // that doesn't belong to the current tracking ID.
            const isTracker = src.includes("mail-tracker-with-new") || 
                              src.includes("api/track/pixel") || 
                              img.hasAttribute("data-mt-pixel") ||
                              style.includes("left:-9999px") ||
                              (img.getAttribute("width") === "1" && img.getAttribute("height") === "1");
            
            if (isTracker && img.getAttribute("data-mt-pixel") !== info.tid) {
              const wrap = img.closest('.mt-wrapper');
              if (wrap) wrap.remove();
              else img.remove();
            }
          });

          // 2. Ensure our correct pixel is present
          if (!body.querySelector(`img[data-mt-pixel="${info.tid}"]`)) {
            const pixelHtml = `<img src="${info.pixel_url}" width="1" height="1" data-mt-pixel="${info.tid}" style="display:block;width:1px;height:1px;opacity:0;border:0;position:absolute;left:-9999px;" alt="" />`;
            body.insertAdjacentHTML("beforeend", `<div class="mt-wrapper" style="opacity:0;height:0;overflow:hidden;">${pixelHtml}</div>`);
          }
        }
      }
    });
  }

  // ---------- Render sent-folder ticks ----------
  function normalizeSubject(s) {
    return (s || "").toLowerCase().replace(/^(re|fwd):\s*/i, "").trim();
  }

  async function loadEmails() {
    try {
      const list = await api("/api/emails/by-ext");
      STATE.sentMap = {};
      list.forEach((e) => {
        const k = normalizeSubject(e.subject);
        if (!k) return;
        if (!STATE.sentMap[k] || new Date(e.sent_at) > new Date(STATE.sentMap[k].sent_at)) {
          STATE.sentMap[k] = e;
        }
      });
    } catch {}
  }

  function makeTickEl(email) {
    const tick = document.createElement("span");
    tick.className = "mt-tick " + (email.open_count > 0 ? "mt-tick-open" : "mt-tick-sent");
    tick.setAttribute("data-mt-id", email.id);
    tick.title = email.open_count > 0
      ? `Opened ${email.open_count}× · last ${new Date(email.last_opened_at).toLocaleString()}`
      : "Sent · not opened yet";
    tick.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="square"><path d="M2 12l5 5L14 8"/><path d="M12 17l9-9"/></svg>';
    return tick;
  }

  function renderTicks() {
    // Gmail row structures (covers Sent, Inbox, search views)
    const rows = document.querySelectorAll('tr.zA, tr[role="row"]');
    rows.forEach((row) => {
      // Find subject cell
      const subjEl = row.querySelector(".bog") || row.querySelector(".y6 span");
      if (!subjEl) return;
      const subject = normalizeSubject(subjEl.innerText);
      const match = STATE.sentMap[subject];
      if (!match) return;

      const existing = subjEl.querySelector(".mt-tick");
      if (existing) {
        // Update state if open_count changed
        if (existing.getAttribute("data-mt-id") === match.id) {
          const shouldBeOpen = match.open_count > 0;
          const isOpen = existing.classList.contains("mt-tick-open");
          if (shouldBeOpen !== isOpen) {
            existing.replaceWith(makeTickEl(match));
          }
          return;
        }
        existing.remove();
      }
      subjEl.prepend(makeTickEl(match));
    });
  }

  // Detect when the user opens their own tracked email in Gmail and ping backend
  // so the next ~90s of pixel hits are classified as self-view (scans).
  const markedViewingAt = {};
  async function markViewing(tid) {
    const now = Date.now();
    if (markedViewingAt[tid] && now - markedViewingAt[tid] < 30000) return;
    markedViewingAt[tid] = now;
    try {
      await api(`/api/track/${tid}/mark-viewing`, { method: "POST" });
      log("self-viewing marked", tid);
    } catch (e) {
      console.warn("[MailTrack] mark-viewing failed", e);
    }
  }

  function detectSelfViewing() {
    try {
      // Only mark as self-viewing if we are in a "Sent" context
      const isSentContext = window.location.hash.includes("sent") || 
                           window.location.hash.includes("label/sent") ||
                           document.querySelector('.nZ') || // Sent label active in sidebar
                           window.location.href.includes("sent");
      
      if (!isSentContext) return;

      // Thread view — subject in opened conversation header
      const h2 = document.querySelector("h2[data-thread-perm-id], .hP");
      if (h2) {
        const subject = normalizeSubject(h2.innerText);
        const match = STATE.sentMap[subject];
        if (match) markViewing(match.id);
      }
    } catch (e) {}
  }

  // Monitor for self-viewing only in sent context
  setInterval(detectSelfViewing, 2000); 

  // --- Extension-Assisted Tracking (Bypasses Google Image Proxy) ---
  const markedOpenedAt = {};
  function detectEmailOpened() {
    try {
      // If we are in the Sent folder, we don't want to trigger this (it would be a self-view)
      const isSentContext = window.location.hash.includes("sent") || 
                           window.location.hash.includes("label/sent") ||
                           document.querySelector('.nZ');
      if (isSentContext) return;

      // Are we looking at an opened email thread?
      const h2 = document.querySelector("h2[data-thread-perm-id], .hP");
      if (!h2) return;

      // Look for any tracking pixels in the currently opened email body
      const trackers = document.querySelectorAll('img[src*="api/track/pixel"], img[src*="api%2Ftrack%2Fpixel"], img[data-mt-pixel], .mt-wrapper img');
      trackers.forEach(img => {
        let tid = img.getAttribute("data-mt-pixel");
        if (!tid) {
          let src = img.src || "";
          try { src = decodeURIComponent(src); } catch(e) {}
          const match = src.match(/\/api\/track\/pixel\/([^.]+)\.png/);
          if (match) tid = match[1];
        }
        
        if (tid) {
          const now = Date.now();
          // Debounce 10 seconds locally to avoid spamming the backend
          if (markedOpenedAt[tid] && now - markedOpenedAt[tid] < 10000) return;
          markedOpenedAt[tid] = now;
          
          api(`/api/track/${tid}/extension-open`, { method: "POST" })
            .catch(e => console.warn("[MailTrack] extension-open failed", e));
        }
      });
    } catch (e) {}
  }

  setInterval(detectEmailOpened, 2000);



  // ---------- Main loop ----------
  async function tick() {
    attachToCompose();

    if (STATE.dead || !isContextAlive()) { STATE.dead = true; return; }
    STATE.config = await getConfig();
    if (STATE.dead) return;
    if (!STATE.config?.backend_url || !STATE.config?.ext_api_key) return;
    await attachToCompose();
    await loadEmails();
    renderTicks();
    detectSelfViewing();
    connectSSE();
  }

  let eventSource = null;
  function connectSSE() {
    if (eventSource) return;
    if (!STATE.config?.backend_url || !STATE.config?.ext_api_key) return;
    
    const url = `${STATE.config.backend_url}/api/stream?key=${STATE.config.ext_api_key}`;
    eventSource = new EventSource(url);
    
    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "open") {
          // Tell background to show notification instantly
          chrome.runtime.sendMessage({
            type: "SHOW_INSTANT_NOTIFICATION",
            tracked_id: data.tracked_id,
            title: "Just opened mail",
            message: `${data.recipient}\nSubject: ${data.subject || "(no subject)"}`
          });
          // Also update local ticks immediately
          loadEmails().then(renderTicks);
        }
      } catch(err) {}
    };
    
    eventSource.onerror = () => {
      eventSource.close();
      eventSource = null;
    };
  }

  const obs = new MutationObserver(() => {
    if (STATE.dead) { obs.disconnect(); return; }
    if (!STATE.config?.backend_url) return;
    attachToCompose();
    renderTicks();
  });
  obs.observe(document.body, { childList: true, subtree: true });

  try {
    chrome.storage.onChanged.addListener((c) => {
      if (STATE.dead) return;
      if (c.backend_url || c.ext_api_key) tick();
    });
  } catch (e) { /* context invalidated */ }

  const pollInterval = setInterval(() => {
    if (STATE.dead) { clearInterval(pollInterval); return; }
    tick();
  }, 5000);
  tick();
  log("content script v0.3.1 loaded");
})();
