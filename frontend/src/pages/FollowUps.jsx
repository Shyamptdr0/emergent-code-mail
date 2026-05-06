import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Send, CheckCircle2, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

function fmt(iso) { return iso ? new Date(iso).toLocaleString() : "—"; }

export default function FollowUps() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/follow-ups").then(({ data }) => setRows(data));
  useEffect(() => { load(); }, []);

  const markSent = async (fid) => {
    await api.post(`/follow-ups/${fid}/mark-sent`);
    toast.success("Marked as sent");
    load();
  };
  const remove = async (fid) => {
    if (!window.confirm("Delete this follow-up?")) return;
    await api.delete(`/follow-ups/${fid}`);
    load();
  };

  return (
    <div data-testid="followups-page">
      <h1 className="text-4xl tracking-tighter font-black mb-6">Follow-ups</h1>
      <div className="bg-white border border-slate-200">
        {rows.length === 0 && (
          <div className="p-12 text-center text-slate-500 text-sm" data-testid="followups-empty">
            No follow-ups scheduled. Open a tracked email and click "Follow-up".
          </div>
        )}
        {rows.map((f) => (
          <div key={f.id} className="px-6 py-5 border-b border-slate-100 last:border-0" data-testid={`followup-${f.id}`}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] tracking-[0.2em] uppercase font-bold px-2 py-0.5 ${f.sent ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"}`}>
                    {f.sent ? "sent" : f.mode}
                  </span>
                  <Link to={`/emails/${f.tracked_email_id}`} className="text-sm font-medium hover:underline">
                    {f.subject}
                  </Link>
                </div>
                <p className="text-xs font-mono text-slate-500 mb-2">to {f.recipient}</p>
                <p className="text-sm text-slate-700 line-clamp-2">{f.message}</p>
                <p className="text-xs text-slate-500 mt-2">
                  Scheduled: {fmt(f.scheduled_at)} {f.sent && f.sent_at && ` · Sent ${fmt(f.sent_at)}`}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                {!f.sent && (
                  <Button data-testid={`mark-sent-${f.id}`} onClick={() => markSent(f.id)} className="bg-[#10B981] hover:bg-emerald-600 rounded-sm h-9 px-3 text-xs">
                    <CheckCircle2 className="w-4 h-4 mr-1" /> Mark sent
                  </Button>
                )}
                <Button data-testid={`delete-${f.id}`} onClick={() => remove(f.id)} variant="outline" className="border-slate-300 rounded-sm h-9 px-3">
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
