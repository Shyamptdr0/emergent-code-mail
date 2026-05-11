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
    
    // Normalize baseUrl: remove trailing slash and trailing /api
    let baseUrl = cfg.backend_url.trim().replace(/\/+$/, "");
    if (baseUrl.toLowerCase().endsWith("/api")) {
      baseUrl = baseUrl.substring(0, baseUrl.length - 4);
    }
    
    // Construct clean URL
    let cleanPath = path.trim();
    if (!cleanPath.startsWith("/")) cleanPath = "/" + cleanPath;
    
    // If the path already starts with /api but the baseUrl ends with /api, remove one
    if (cleanPath.startsWith("/api/") && baseUrl.toLowerCase().endsWith("/api")) {
      baseUrl = baseUrl.substring(0, baseUrl.length - 4);
    }
    // If neither have /api, add it
    if (!cleanPath.startsWith("/api/") && !baseUrl.toLowerCase().endsWith("/api")) {
      baseUrl = baseUrl + "/api";
    }

    const finalUrl = baseUrl + cleanPath;
    const r = await fetch(finalUrl, {
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
                              src.includes("api%2Ftrack%2Fpixel") ||
                              img.hasAttribute("data-mt-pixel") ||
                              style.includes("left:-9999px") ||
                              (img.getAttribute("width") === "1" && img.getAttribute("height") === "1") ||
                              (img.getAttribute("alt") || "").startsWith("mt-");
            
            if (isTracker && img.getAttribute("data-mt-pixel") !== info.tid && img.getAttribute("alt") !== `mt-${info.tid}`) {
              const wrap = img.closest('.mt-wrapper');
              if (wrap) wrap.remove();
              else img.remove();
            }
          });

          // 2. Ensure our correct pixel is present
          if (!body.querySelector(`img[data-mt-pixel="${info.tid}"], img[alt="mt-${info.tid}"]`)) {
            const pixelHtml = `<img src="${info.pixel_url}" width="1" height="1" data-mt-pixel="${info.tid}" alt="mt-${info.tid}" style="display:block;width:1px;height:1px;opacity:0;border:0;position:absolute;left:-9999px;" />`;
            body.insertAdjacentHTML("beforeend", `<div class="mt-wrapper" style="opacity:0;height:0;overflow:hidden;">${pixelHtml}</div>`);
          }
        }
      }
    });
  }

  // ---------- Render sent-folder ticks ----------
  function normalizeSubject(s) {
    let subject = (s || "").toLowerCase();
    // Recursively remove ALL prefixes like Re:, Fwd:, AW:, etc.
    const prefixRegex = /^(re|fwd|aw|antw|wg|reply|forward|回复|转发):\s*/i;
    while (prefixRegex.test(subject)) {
      subject = subject.replace(prefixRegex, "");
    }
    return subject.trim();
  }

  async function loadEmails() {
    try {
      const list = await api("/api/emails/by-ext");
      STATE.sentMap = {};
      list.forEach((e) => {
        const k = normalizeSubject(e.subject);
        if (!k) return;
        // Keep the most recent one if duplicates exist
        if (!STATE.sentMap[k] || new Date(e.sent_at) > new Date(STATE.sentMap[k].sent_at)) {
          STATE.sentMap[k] = e;
        }
      });
    } catch (err) {
      console.warn("[MailTrack] loadEmails failed", err);
    }
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

  // Detect if a tracked email has been replied to
  const pendingReplied = new Set();
  async function detectReplies() {
    if (STATE.dead || !STATE.config?.backend_url) return;
    
    // 1. SCAN INBOX ROWS (List View)
    const rows = document.querySelectorAll('tr.zA, tr[role="row"]');
    rows.forEach((row) => {
      const subjEl = row.querySelector(".bog, .y6 span, .y2, .bAW");
      if (!subjEl) return;
      
      const subjectText = subjEl.innerText || "";
      const normalized = normalizeSubject(subjectText);
      const match = STATE.sentMap[normalized];
      
      if (match && !match.replied && !pendingReplied.has(match.id)) {
        const countEl = row.querySelector(".at, .byY, .bsU, .amH, .as, .bsU");
        const countText = countEl?.innerText || "";
        const countMatch = countText.match(/(\d+)/);
        const count = countMatch ? parseInt(countMatch[1]) : 1;

        const labels = row.innerText || "";
        const hasInboxLabel = labels.includes("Inbox") || !!row.querySelector('div[aria-label="Inbox"]');
        const isSentFolder = window.location.hash.includes("sent") || window.location.href.includes("sent");
        
        // PROACTIVE SENDER CHECK:
        const senderEl = row.querySelector(".yP, .yW, .bA4, .zF, .vW");
        const senderText = senderEl?.innerText || "";
        
        const myName = STATE.userProfile?.name?.toLowerCase();
        const myEmail = STATE.userProfile?.email?.toLowerCase();
        
        // Gmail thread sender list is usually "Person1, Person2, me (3)"
        const senderParts = senderText.split(/[,，]/).map(s => s.trim().toLowerCase());
        
        // Is there someone in this list who is NOT me?
        const hasOthersInSenderList = senderParts.some(s => {
          if (!s || s === "me" || s === "to:") return false;
          if (myName && s.includes(myName)) return false;
          if (myEmail && s.includes(myEmail)) return false;
          return true;
        });
        
        const isUnread = row.classList.contains("zE");

        // Logic: Count as reply if there are multiple messages AND someone else is in the list,
        // OR if it's an unread message from someone else.
        if (!isSentFolder && hasOthersInSenderList && (count > 1 || isUnread || hasInboxLabel)) {
          markReplied(match, subjectText, `Auto-detected from Inbox List (Senders: ${senderText}, Count: ${count})`);
        }
      }
    });

    // 2. SCAN OPEN THREAD VIEW
    const threadHeader = document.querySelector("h2[data-thread-perm-id], .hP");
    if (threadHeader) {
      const subjectText = threadHeader.innerText || "";
      const normalized = normalizeSubject(subjectText);
      const match = STATE.sentMap[normalized];
      
      if (match && !match.replied && !pendingReplied.has(match.id)) {
        // Look at message containers
        const messages = document.querySelectorAll(".adn, .kv, .h7, .gE, .btm");
        if (messages.length > 1) {
          // Check if any message is NOT from me
          let foundRecipientReply = false;
          const myName = STATE.userProfile?.name?.toLowerCase();
          const myEmail = STATE.userProfile?.email?.toLowerCase();

          messages.forEach(msg => {
            const sender = msg.querySelector(".zF, .vW, .gD")?.innerText || "";
            if (sender) {
              const sLow = sender.toLowerCase();
              let isMe = sLow.includes("me");
              if (!isMe && myName && sLow.includes(myName)) isMe = true;
              if (!isMe && myEmail && sLow.includes(myEmail)) isMe = true;
              
              if (!isMe) foundRecipientReply = true;
            }
          });
          
          if (foundRecipientReply) {
            markReplied(match, subjectText, `Detected from Thread View (${messages.length} messages, reply found)`);
          }
        }
      }
    }
  }

  async function markReplied(match, subject, reason) {
    if (pendingReplied.has(match.id)) return;
    pendingReplied.add(match.id);
    log("Reply detected, verifying with server:", subject, reason);
    
    try {
      const res = await api(`/api/track/${match.id}/mark-replied`, { method: "POST" });
      
      if (res.verified) {
        log("Successfully verified and marked as replied:", subject);
        match.replied = true; 
        
        chrome.runtime.sendMessage({
          type: "SHOW_INSTANT_NOTIFICATION",
          tracked_id: match.id,
          title: "Reply Detected! 🎯",
          message: `Lead: ${match.recipient}\nAll sequences stopped.`
        });

        loadEmails().then(renderTicks);
      } else {
        log("Reply detection rejected by server verification", subject, res.status);
        pendingReplied.delete(match.id);
      }
    } catch (e) {
      console.warn("[MailTrack] mark-replied failed", e);
      pendingReplied.delete(match.id);
    }
  }

  // Detect when the user opens their own tracked email in Gmail and ping backend
  // so the next ~90s of pixel hits are classified as self-view (scans).
  const markedViewingAt = {};
  async function markViewing(tid) {
    const now = Date.now();
    // Use a 2-second debounce so it constantly refreshes the backend's 4-second shield
    if (markedViewingAt[tid] && now - markedViewingAt[tid] < 2000) return;
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
      // Find all tracking pixels in the currently visible view
      // We look for the 'alt' attribute because Gmail preserves 'alt' even when it completely obfuscates the 'src' URL
      const trackers = document.querySelectorAll('img[alt^="mt-"], img[data-mt-pixel], img[src*="track/pixel"], img[src*="track%2Fpixel"], .mt-wrapper img');
      trackers.forEach(img => {
        let tid = img.getAttribute("data-mt-pixel");
        if (!tid) {
          const alt = img.getAttribute("alt") || "";
          if (alt.startsWith("mt-")) {
            tid = alt.replace("mt-", "");
          }
        }
        if (!tid) {
          let src = img.src || "";
          try { src = decodeURIComponent(src); } catch(e) {}
          const match = src.match(/\/api\/track\/pixel\/([^.]+)\.png/);
          if (match) tid = match[1];
        }
        if (tid) markViewing(tid);
      });
    } catch (e) {}
  }

  // Monitor for self-viewing aggressively (500ms)
  setInterval(detectSelfViewing, 500); 

  // --- Extension-Assisted Tracking (Bypasses Google Image Proxy) ---
  const markedOpenedAt = {};
  let currentlyViewingThread = false;

  function detectEmailOpened() {
    try {
      // If we are in the Sent folder, we don't want to trigger this (it would be a self-view)
      const isSentContext = window.location.hash.includes("sent") || 
                           window.location.hash.includes("label/sent") ||
                           document.querySelector('.nZ');
      if (isSentContext) {
        currentlyViewingThread = false;
        return;
      }

      // Are we looking at an opened email thread?
      const h2 = document.querySelector("h2[data-thread-perm-id], .hP");
      if (!h2) {
        // User left the email view (e.g. back to Inbox)
        currentlyViewingThread = false;
        // Clear local debounce so immediate re-entry counts as a new open
        for (const key in markedOpenedAt) delete markedOpenedAt[key];
        return;
      }

      if (currentlyViewingThread) return; // We already counted this specific entrance into the thread

      // Look for any tracking pixels in the currently opened email body
      const trackers = document.querySelectorAll('img[src*="api/track/pixel"], img[src*="api%2Ftrack%2Fpixel"], img[data-mt-pixel], .mt-wrapper img');
      let foundTid = null;
      trackers.forEach(img => {
        let tid = img.getAttribute("data-mt-pixel");
        if (!tid) {
          let src = img.src || "";
          try { src = decodeURIComponent(src); } catch(e) {}
          const match = src.match(/\/api\/track\/pixel\/([^.]+)\.png/);
          if (match) tid = match[1];
        }
        if (tid) foundTid = tid;
      });
        
      if (foundTid) {
        currentlyViewingThread = true;
        const now = Date.now();
        // 1-second local debounce just to prevent double-firing in rapid DOM mutations
        if (markedOpenedAt[foundTid] && now - markedOpenedAt[foundTid] < 1000) return;
        markedOpenedAt[foundTid] = now;
        
        api(`/api/track/${foundTid}/extension-open`, { method: "POST" })
          .catch(e => console.warn("[MailTrack] extension-open failed", e));
      }
    } catch (e) {}
  }

  // Run this very frequently so rapid tab-switching is caught
  setInterval(detectEmailOpened, 500);



  // ---------- Main loop ----------
  async function tick() {
    attachToCompose();

    if (STATE.dead || !isContextAlive()) { STATE.dead = true; return; }
    STATE.config = await getConfig();
    if (STATE.dead) return;
    if (!STATE.config?.backend_url || !STATE.config?.ext_api_key) return;

    // Fetch user profile to avoid self-reply detection
    try {
      const profile = await api("/api/ext-profile");
      STATE.userProfile = profile;
    } catch (e) {
      console.warn("[MailTrack] profile fetch failed", e);
      // Fallback: Try to find user identity in Gmail UI (top right account switcher)
      const accountLabel = document.querySelector('a[aria-label*="Google Account:"]')?.getAttribute('aria-label') || "";
      if (accountLabel) {
        // e.g. "Google Account: Name (email@gmail.com)"
        const match = accountLabel.match(/Google Account:\s*(.*?)\s*\((.*?)\)/i);
        if (match) {
          STATE.userProfile = { name: match[1], email: match[2] };
          log("[MailTrack] Fallback identity detected from Gmail UI:", STATE.userProfile);
        }
      }
    }

    await attachToCompose();
    await loadEmails();
    renderTicks();
    detectReplies();
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

  function injectTopIcon() {
    if (document.getElementById("mt-dashboard-link")) return;
    
    // Find the settings gear
    const settingsBtn = document.querySelector('div[aria-label="Settings"], a[aria-label="Settings"]');
    if (!settingsBtn) return;

    // Gmail wraps icons in a button-like div. We need to be a sibling of THAT wrapper.
    const wrapper = settingsBtn.closest('.gb_A, .gb_ve, div[role="button"]') || settingsBtn.parentElement;
    if (!wrapper || !wrapper.parentNode) return;

    const link = document.createElement("a");
    link.id = "mt-dashboard-link";
    link.href = "https://emergent-code-mail.vercel.app";
    link.target = "_blank";
    link.title = "Open MailTrack Dashboard";
    link.style.cssText = "display:inline-flex !important; align-items:center; justify-content:center; width:40px; height:40px; border-radius:50%; transition:background 0.2s; cursor:pointer; margin-right:4px; vertical-align:middle; text-decoration:none;";
    
    link.onmouseover = () => link.style.background = "rgba(60, 64, 67, 0.08)";
    link.onmouseout = () => link.style.background = "transparent";

    link.innerHTML = `
      <div style="background: #10b981; width: 22px; height: 22px; border-radius: 6px; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 2px rgba(0,0,0,0.15);">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="white" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 12l5 5L14 8"/><path d="M12 17l9-9"/>
        </svg>
      </div>
    `;

    // Insert as a sibling to the WRAPPER to ensure horizontal flex alignment
    wrapper.parentNode.insertBefore(link, wrapper);
  }

  function showToast(msg) {
    const id = "mt-toast-" + Date.now();
    const div = document.createElement("div");
    div.id = id;
    div.style.cssText = "position:fixed; bottom:20px; left:20px; background:#1e293b; color:white; padding:12px 16px; border-radius:12px; font-family:Inter, sans-serif; font-size:13px; z-index:999999; display:flex; align-items:center; gap:12px; box-shadow:0 10px 15px -3px rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); transform:translateY(100px); transition:transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); cursor:pointer;";
    div.innerHTML = `
      <div style="background:#10b981; width:24px; height:24px; border-radius:6px; display:flex; align-items:center; justify-content:center; shrink:0;">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      </div>
      <div style="flex:1;">
        <div style="font-weight:bold; margin-bottom:1px; display:flex; align-items:center; gap:6px;">
          Email Opened!
          <span style="font-size:9px; background:rgba(255,255,255,0.1); padding:1px 4px; border-radius:4px; opacity:0.7;">INSTANT</span>
        </div>
        <div style="opacity:0.8; font-size:11px;">${msg}</div>
      </div>
    `;
    div.onclick = () => div.remove();
    document.body.appendChild(div);
    setTimeout(() => div.style.transform = "translateY(0)", 100);
    setTimeout(() => {
      div.style.transform = "translateY(100px)";
      setTimeout(() => div.remove(), 300);
    }, 5000);
  }

  function initSSE() {
    if (STATE.sse || !STATE.config?.backend_url || !STATE.config?.ext_api_key) return;
    
    // Normalize baseUrl
    let baseUrl = STATE.config.backend_url.trim().replace(/\/+$/, "");
    if (baseUrl.toLowerCase().endsWith("/api")) {
      baseUrl = baseUrl.substring(0, baseUrl.length - 4);
    }
    
    const url = `${baseUrl}/api/events/stream?key=${STATE.config.ext_api_key}`;
    log("[SSE] Connecting to:", url);
    
    try {
      const es = new EventSource(url);
      STATE.sse = es;
      
      es.onopen = () => {
        log("[SSE] Connection established and active");
      };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "open") {
            log("[SSE] Instant open detected:", data);
            showToast(`${data.recipient} opened your email: ${data.subject}`);
            renderTicks();
          } else if (data.type === "reply") {
            log("[SSE] Instant reply detected:", data);
            showToast(`🎯 NEW REPLY from ${data.recipient}! Moving to Active.`);
            renderTicks();
          }
        } catch (err) {}
      };
      
      es.onerror = (e) => {
        log("[SSE] Connection error, retrying in 10s...");
        es.close();
        STATE.sse = null;
      };
    } catch (e) {
      log("[SSE] Setup failed:", e);
      STATE.sse = null;
    }
  }

  // Call injectTopIcon inside tick or main loop
  setInterval(() => {
    injectTopIcon();
    initSSE();
  }, 3000);

  log("content script v0.4.0 loaded with Real-Time Support");
})();
