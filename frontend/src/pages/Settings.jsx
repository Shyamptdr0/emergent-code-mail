import { useState } from "react";
import { Copy, RefreshCw, Download } from "lucide-react";
import { api, BACKEND_URL } from "../lib/api";
import { Button } from "../components/ui/button";
import { useAuth } from "../lib/AuthContext";
import { toast } from "sonner";

export default function Settings() {
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState(false);

  const copy = (txt) => {
    if (!txt) return;
    try {
      // Fallback: hidden textarea + execCommand (works inside sandboxed iframes)
      const ta = document.createElement("textarea");
      ta.value = txt;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) { toast.success("Copied"); return; }
    } catch (e) {}
    // Modern API as secondary attempt
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(txt).then(
        () => toast.success("Copied"),
        () => toast.error("Copy blocked — select & copy manually")
      );
    } else {
      toast.error("Copy blocked — select & copy manually");
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate key? Old key will stop working immediately.")) return;
    setBusy(true);
    try {
      await api.post("/auth/rotate-ext-key");
      await refresh();
      toast.success("Key rotated");
    } finally {
      setBusy(false);
    }
  };

  const config = `BACKEND_URL=${BACKEND_URL}\nEXT_API_KEY=${user?.ext_api_key || ""}`;

  return (
    <div className="space-y-10" data-testid="settings-root">
      <h1 className="text-4xl tracking-tighter font-black">Settings</h1>

      <Section title="Extension setup" subtitle="Install the Chrome extension and paste your key.">
        <div className="space-y-3">
          <div>
            <p className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500 mb-2">Backend URL</p>
            <CopyRow value={BACKEND_URL} onCopy={() => copy(BACKEND_URL)} testid="backend-url-row" />
          </div>
          <div>
            <p className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500 mb-2">Extension API key</p>
            <CopyRow value={user?.ext_api_key} onCopy={() => copy(user?.ext_api_key)} testid="ext-key-row" mono />
          </div>
          <div className="flex gap-2">
            <Button onClick={rotate} disabled={busy} variant="outline" className="border-slate-300 rounded-sm" data-testid="rotate-key-btn">
              <RefreshCw className="w-4 h-4 mr-2" /> Rotate key
            </Button>
            <Button onClick={() => copy(config)} className="bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm" data-testid="copy-config-btn">
              <Copy className="w-4 h-4 mr-2" /> Copy config
            </Button>
          </div>
        </div>
      </Section>

      <Section title="Install the extension" subtitle="Step-by-step.">
        <ol className="list-decimal pl-5 space-y-3 text-sm text-slate-700">
          <li>Download the extension folder from the project (<code className="font-mono text-xs bg-slate-100 px-1.5 py-0.5">/app/extension</code>).</li>
          <li>Open <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5">chrome://extensions</span> in Chrome.</li>
          <li>Toggle <strong>Developer mode</strong> (top right), then click <strong>Load unpacked</strong>.</li>
          <li>Select the extension folder. The MailTrack icon will appear in your toolbar.</li>
          <li>Click the icon, paste the <strong>Backend URL</strong> and <strong>API key</strong> shown above, save.</li>
          <li>Open Gmail. Compose a new email — it will be tracked automatically. Sent items show gray ticks (default) and turn green when opened.</li>
        </ol>
        <div className="mt-6">
          <a
            href={`${BACKEND_URL}/api/download/extension`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="download-ext-link"
            className="inline-flex items-center gap-2 bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm font-medium px-6 py-2.5 text-sm transition-colors cursor-pointer"
          >
            <Download className="w-4 h-4" /> Download extension zip
          </a>
          <p className="text-xs text-slate-500 mt-3 font-mono leading-relaxed">
            If blocked: copy link → open in new tab →{" "}
            <code className="bg-slate-100 px-1 py-0.5">{BACKEND_URL}/api/download/extension</code>
          </p>
        </div>
      </Section>

      <Section title="Full source code" subtitle="Download the complete project (backend + frontend + extension) for GitHub.">
        <p className="text-sm text-slate-700 mb-4">
          Includes FastAPI backend, React dashboard, and the Chrome extension — ready to push to your own GitHub repo.
        </p>
        <a
          href={`${BACKEND_URL}/api/download/source`}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="download-source-btn"
          className="inline-flex items-center gap-2 bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm font-medium px-6 py-2.5 text-sm transition-colors cursor-pointer"
        >
          <Download className="w-4 h-4" /> Download full source (.zip)
        </a>
        <p className="text-xs text-slate-500 mt-3 font-mono leading-relaxed">
          If blocked: copy link → open in new tab →{" "}
          <code className="bg-slate-100 px-1 py-0.5">{BACKEND_URL}/api/download/source</code>
        </p>
      </Section>
    </div>
  );
}

function Section({ title, subtitle, children }) {
  return (
    <section className="bg-white border border-slate-200 p-8">
      <h2 className="text-2xl tracking-tight font-bold mb-1">{title}</h2>
      {subtitle && <p className="text-sm text-slate-500 mb-6">{subtitle}</p>}
      {children}
    </section>
  );
}

function CopyRow({ value, onCopy, testid, mono }) {
  return (
    <div className="flex items-center gap-2" data-testid={testid}>
      <code className={`flex-1 px-4 py-3 bg-slate-50 border border-slate-200 text-sm overflow-x-auto ${mono ? "font-mono" : ""}`}>
        {value || "—"}
      </code>
      <Button onClick={onCopy} variant="outline" className="border-slate-300 rounded-sm shrink-0" size="icon">
        <Copy className="w-4 h-4" />
      </Button>
    </div>
  );
}
