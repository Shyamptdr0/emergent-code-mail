import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCheck, Calendar, Trash2, ArrowRight } from "lucide-react";
import { api, API } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatRel(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (Math.abs(diff) < 60) return "just now";
  
  const absDiff = Math.abs(diff);
  const suffix = diff > 0 ? 'ago' : 'from now';
  
  if (absDiff < 3600) return `${Math.floor(absDiff / 60)}m ${suffix}`;
  if (absDiff < 86400) return `${Math.floor(absDiff / 3600)}h ${suffix}`;
  if (absDiff < 86400 * 30) return `${Math.floor(absDiff / 86400)}d ${suffix}`;
  
  return d.toLocaleDateString();
}

export default function FollowUps() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const { data } = await api.get("/follow-ups");
      setRows(data);
    } catch (e) {
      toast.error("Failed to load follow-ups");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { 
    load(); 
    // SSE listener for real-time updates
    const url = `${API}/events/stream`;
    const es = new EventSource(url, { withCredentials: true });
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "followup_sent" || data.type === "open" || data.type === "reply") {
          load();
        }
      } catch {}
    };
    return () => es.close();
  }, []);

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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Follow-up Pipeline</h1>
        <div className="flex gap-2">
           <div className="px-3 py-1 bg-white border border-slate-200 rounded text-[10px] font-bold uppercase text-slate-500 shadow-sm">
             {rows.filter(r => !r.sent).length} Scheduled
           </div>
        </div>
      </div>

      {loading ? (
        <div className="bg-white border border-slate-200 rounded p-20 flex flex-col items-center justify-center">
          <div className="loader mb-4" />
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest animate-pulse">Syncing Pipeline...</p>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50">
                  <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Status</th>
                  <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Subject & Message</th>
                  <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Recipient</th>
                  <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Timing</th>
                  <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {rows.length === 0 ? (
                  <tr><td colSpan="5" className="px-4 py-12 text-center text-slate-400 text-sm">No follow-ups scheduled</td></tr>
                ) : (
                rows.map((f) => (
                  <tr key={f.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {f.sent ? (
                          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-emerald-50 text-emerald-600 rounded-full border border-emerald-100 shadow-sm">
                            <CheckCheck className="w-3 h-3" strokeWidth={3} />
                            <span className="text-[9px] font-black uppercase tracking-tight">Sent</span>
                          </div>
                        ) : f.status === 'stopped' ? (
                          <div className="px-2 py-0.5 bg-slate-100 text-slate-400 rounded-full border border-slate-200">
                             <span className="text-[9px] font-black uppercase tracking-tight">Stopped</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                             <div className="w-4 h-4 rounded-full border-2 border-slate-100 border-t-blue-500 animate-spin" />
                             <span className="text-[10px] font-bold text-blue-600 uppercase tracking-tighter">Counting Down</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <Link to={`/emails/${f.tracked_email_id}`} className="text-sm font-bold text-slate-900 hover:underline block truncate">
                        {f.subject}
                      </Link>
                      <p className="text-[11px] text-slate-500 line-clamp-1 italic mt-0.5">"{f.message}"</p>
                    </td>
                    <td className="px-4 py-3">
                       <div className="text-sm text-slate-600 font-medium">{f.recipient}</div>
                       <div className="text-[9px] font-black uppercase tracking-tight text-slate-400">{f.mode} · {f.trigger_condition.replace('if_','').replace('_',' ')}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-bold text-slate-900">
                        {f.sent ? formatRel(f.sent_at) : (
                          <div className="flex items-center gap-1">
                             <Calendar className="w-3 h-3 text-blue-500" />
                             {formatRel(f.scheduled_at)}
                          </div>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {f.sent ? `Sent ${fmt(f.sent_at)}` : `Scheduled ${fmt(f.scheduled_at)}`}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {!f.sent && (
                          <button 
                            onClick={() => markSent(f.id)} 
                            className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
                            title="Mark as Sent"
                          >
                            <Calendar className="w-4 h-4" />
                          </button>
                        )}
                        <button 
                          onClick={() => remove(f.id)} 
                          className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table>
        </div>
      </div>
      )}
    </div>
  );
}
