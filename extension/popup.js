const $ = (id) => document.getElementById(id);

function setStatus(text, cls) {
  const el = $("status");
  el.textContent = text;
  el.className = "status " + (cls || "");
}

function setMessage(text, cls) {
  const el = $("save-msg");
  if (!el) return;
  el.textContent = text || "";
  el.className = "save-msg " + (cls || "");
}

async function load() {
  chrome.storage.sync.get(["backend_url", "ext_api_key"], async (v) => {
    v = v || {};
    // Pre-fill the inputs (so user can see what's saved)
    $("backend").value = v.backend_url || "";
    $("apikey").value = v.ext_api_key || "";

    if (v.backend_url && v.ext_api_key) {
      const ok = await showRecent(v);
      if (!ok) {
        // Auth failed — keep config visible WITH inputs filled, show error
        $("config").hidden = false;
        $("recent").hidden = true;
      }
    } else {
      $("config").hidden = false;
      $("recent").hidden = true;
      setStatus("setup", "");
      setMessage("");
    }
  });
}

async function showRecent(cfg) {
  setStatus("checking…", "");
  try {
    const r = await fetch(cfg.backend_url + "/api/emails/by-ext", {
      headers: { "X-Ext-Key": cfg.ext_api_key },
    });
    if (r.status === 401) {
      setMessage("Invalid API key. Get a fresh key from dashboard → Settings.", "err");
      setStatus("invalid key", "bad");
      return false;
    }
    if (!r.ok) {
      setMessage(`Backend returned ${r.status}. Check the URL.`, "err");
      setStatus("error", "bad");
      return false;
    }
    const rows = await r.json();
    $("config").hidden = true;
    $("recent").hidden = false;
    setStatus("live", "ok");
    const list = $("list");
    list.innerHTML = "";
    if (rows.length === 0) {
      list.innerHTML =
        '<li style="color:#9ca3af;font-size:12px;">Send your first email — it will appear here.</li>';
      return true;
    }
    rows.slice(0, 20).forEach((e) => {
      const li = document.createElement("li");
      const opened = e.open_count > 0;
      li.innerHTML = `
        <svg class="tick ${opened ? "opened" : "sent"}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M2 12l5 5L14 8"/><path d="M12 17l9-9"/></svg>
        <div class="meta">
          <div class="subj">${escapeHtml(e.subject || "(no subject)")}</div>
          <div class="rcpt">${escapeHtml(e.recipient)}</div>
        </div>
        ${opened ? `<span class="cnt">${e.open_count}</span>` : ""}`;
      list.appendChild(li);
    });
    return true;
  } catch (e) {
    setMessage(`Cannot reach backend: ${e.message}. Verify URL & internet.`, "err");
    setStatus("offline", "bad");
    return false;
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

$("save").addEventListener("click", async () => {
  const backend_url = $("backend").value.trim().replace(/\/$/, "");
  const ext_api_key = $("apikey").value.trim();
  if (!backend_url) {
    setMessage("Enter Backend URL", "err");
    return;
  }
  if (!ext_api_key) {
    setMessage("Enter API key", "err");
    return;
  }
  if (!/^https?:\/\//i.test(backend_url)) {
    setMessage("Backend URL must start with http:// or https://", "err");
    return;
  }

  setMessage("Testing connection…", "");
  // Test before saving
  try {
    const r = await fetch(backend_url + "/api/emails/by-ext", {
      headers: { "X-Ext-Key": ext_api_key },
    });
    if (r.status === 401) {
      setMessage("API key invalid. Copy a fresh key from dashboard.", "err");
      return;
    }
    if (!r.ok) {
      setMessage(`Backend returned ${r.status}.`, "err");
      return;
    }
  } catch (e) {
    setMessage(`Cannot reach backend: ${e.message}`, "err");
    return;
  }

  chrome.storage.sync.set({ backend_url, ext_api_key }, () => {
    setMessage("Saved! Loading…", "ok");
    setTimeout(load, 400);
  });
});

$("reset").addEventListener("click", () => {
  chrome.storage.sync.remove(["backend_url", "ext_api_key"], () => {
    setMessage("");
    load();
  });
});

load();
