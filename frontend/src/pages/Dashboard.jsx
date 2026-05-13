import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCheck, Mail, Send, TrendingUp, Eye } from "lucide-react";
import { api, API } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../lib/AuthContext";

function formatRel(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setLoading(true);
      const [s, e] = await Promise.all([api.get("/stats"), api.get("/emails")]);
      setStats(s.data);
      setEmails(e.data);
    } catch (e) {
      toast.error("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // SSE
    const url = `${API}/events/stream`;
    const es = new EventSource(url, { withCredentials: true });
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "open") {
          toast.success(`Email opened: ${data.subject}`, {
            description: `By ${data.recipient} · ${formatRel(data.ts)}`,
          });
          if ("Notification" in window && Notification.permission === "granted") {
            new Notification("MailTrack: Email opened", {
              body: `${data.recipient} opened "${data.subject}"`,
              icon: user?.picture,
            });
          }
          load();
        }
      } catch {}
    };
    es.onerror = () => {};
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
    return () => es.close();
    // eslint-disable-next-line
  }, []);

  return (
    <div data-testid="dashboard-root" className="space-y-10">
      {loading ? (
        <div className="bg-white border border-slate-200 rounded p-20 flex flex-col items-center justify-center">
          <div className="loader mb-4" />
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest animate-pulse">Analyzing your pulse...</p>
        </div>
      ) : (
        <>
          <div>
            <p className="text-xs tracking-[0.25em] uppercase font-bold text-slate-500 mb-3">Welcome back</p>
            <h1 className="text-4xl sm:text-5xl tracking-tighter font-black">{user?.name?.split(" ")[0] || "there"} — here's your inbox pulse.</h1>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="stats-grid">
            <Stat icon={<Mail className="w-4 h-4" />} label="Total Sent" value={stats?.total_sent ?? "—"} testid="stat-sent" />
            <Stat icon={<Eye className="w-4 h-4 text-indigo-500" />} label="Total Opened" value={stats?.total_opened ?? "—"} testid="stat-opened" />
            <Stat icon={<Eye className="w-4 h-4 text-slate-400" />} label="Not Opened" value={stats?.total_not_opened ?? "—"} testid="stat-not-opened" />
            <Stat icon={<TrendingUp className="w-4 h-4 text-emerald-500" />} label="Total Replied" value={stats?.total_replied ?? "—"} testid="stat-replied" />
            <Stat icon={<CheckCheck className="w-4 h-4 text-blue-500" />} label="Follow-ups Sent" value={stats?.follow_ups_sent ?? "—"} testid="stat-fups-sent" />
            <Stat icon={<Send className="w-4 h-4 text-amber-500" />} label="Follow-ups Pending" value={stats?.follow_ups_pending ?? "—"} testid="stat-followups" />
          </div>

          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
              <h2 className="text-2xl tracking-tight font-bold">Recent tracked emails</h2>
              <Link to="/emails" className="text-sm font-medium underline underline-offset-4" data-testid="see-all-link">See all</Link>
            </div>
            <div className="bg-white border border-slate-200" data-testid="recent-emails-list">
              {emails.length === 0 && (
                <div className="p-12 text-center text-slate-500" data-testid="empty-state">
                  <CheckCheck className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm">No tracked emails yet. Install the Chrome extension and send your first email.</p>
                  <Link to="/settings" className="text-sm font-medium underline underline-offset-4 mt-3 inline-block">
                    Setup extension →
                  </Link>
                </div>
              )}
              {emails.slice(0, 8).map((e) => (
                <Link
                  key={e.id}
                  to={`/emails/${e.id}`}
                  data-testid={`email-row-${e.id}`}
                  className="flex items-center gap-4 px-6 py-4 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors"
                >
                  <CheckCheck
                    className={`w-5 h-5 shrink-0 ${e.open_count > 0 ? "text-[#10B981]" : "text-slate-300"}`}
                    strokeWidth={2.5}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-sm truncate">{e.subject || "(no subject)"}</div>
                    <div className="text-xs text-slate-500 truncate font-mono">to {e.recipient}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-xs text-slate-500 font-bold">Sent {formatRel(e.sent_at)}</div>
                    {e.open_count > 0 ? (
                      <div className="text-xs font-bold text-[#10B981]">
                         Opened {formatRel(e.last_opened_at)}
                      </div>
                    ) : (
                      <div className="text-xs text-slate-300 font-bold uppercase tracking-tighter">Not Opened</div>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ icon, label, value, testid }) {
  return (
    <div className="bg-white border border-slate-200 p-4 sm:p-6" data-testid={testid}>
      <div className="flex items-center gap-2 text-slate-500 mb-3">
        {icon}
        <span className="text-xs tracking-[0.2em] uppercase font-bold">{label}</span>
      </div>
      <div className="text-3xl font-black tracking-tighter">{value}</div>
    </div>
  );
}
