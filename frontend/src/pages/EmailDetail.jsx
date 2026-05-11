import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCheck, ArrowLeft, Trash2, MessageCircle, ChevronDown, ChevronUp, Clock, Zap } from "lucide-react";
import { api } from "../lib/api";
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
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function EmailDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [em, setEm] = useState(null);

  const load = useCallback(() => api.get(`/emails/${id}`).then(({ data }) => setEm(data)), [id]);
  useEffect(() => { load(); }, [id, load]);

  const remove = async () => {
    if (!window.confirm("Delete this tracked email?")) return;
    await api.delete(`/emails/${id}`);
    toast.success("Deleted");
    navigate("/emails");
  };

  const [showTimeline, setShowTimeline] = useState(false);

  if (!em) return (
    <div className="flex flex-col items-center justify-center py-40">
      <div className="loader mb-4" />
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest animate-pulse">Retrieving conversation details...</p>
    </div>
  );

  return (
    <div className="space-y-8" data-testid="email-detail-root">
      <button onClick={() => navigate(-1)} className="text-sm flex items-center gap-2 text-slate-600 hover:text-black" data-testid="back-btn">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="bg-white border border-slate-200 p-4 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 mb-3">
              {em.replied ? (
                <>
                  <MessageCircle className="w-6 h-6 shrink-0 text-emerald-500" strokeWidth={2.5} />
                  <span className="text-xs tracking-[0.2em] uppercase font-bold text-emerald-600">Replied</span>
                </>
              ) : (
                <>
                  <CheckCheck
                    className={`w-6 h-6 shrink-0 ${em.open_count > 0 ? "text-[#10B981]" : "text-slate-300"}`}
                    strokeWidth={2.5}
                  />
                  <span className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500">
                    {em.open_count > 0 ? "Opened" : "Not yet opened"}
                  </span>
                </>
              )}
            </div>
            <h1 className="text-3xl tracking-tight font-black break-words">{em.subject || "(no subject)"}</h1>
            <p className="text-sm font-mono text-slate-600 mt-2">to {em.recipient}</p>
            <p className="text-xs text-slate-500 mt-1">
              Sent <span className="font-bold text-slate-900">{formatRel(em.sent_at)}</span> ({fmt(em.sent_at)})
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button data-testid="delete-email-btn" onClick={remove} variant="outline" className="border-slate-300 rounded-sm">
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        {/* Open Timeline Box */}
        <div className="space-y-4">
          <button 
            onClick={() => setShowTimeline(!showTimeline)}
            className="flex items-center justify-between w-full p-4 bg-white border border-slate-200 rounded-xl hover:border-slate-400 transition-all shadow-sm group"
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100 group-hover:bg-white transition-colors">
                <Clock className="w-4 h-4 text-slate-400 group-hover:text-black" />
              </div>
              <div className="text-left">
                <p className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Open Timeline</p>
                <p className="text-sm font-black text-slate-900">{em.open_count} Engagement{em.open_count !== 1 ? 's' : ''}</p>
              </div>
            </div>
            {showTimeline ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
          </button>
          
          {showTimeline && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm animate-in fade-in slide-in-from-top-2 duration-200">
              {em.opens.length === 0 ? (
                <div className="p-10 text-center text-sm text-slate-400 italic">
                  No tracking events recorded yet.
                </div>
              ) : (
                <div className="divide-y divide-slate-50">
                  {em.opens.slice().reverse().map((o, i) => (
                    <div key={i} className="px-5 py-4 hover:bg-slate-50/50 transition-colors flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
                        <span className="text-sm font-bold text-slate-700">{fmt(o.ts)}</span>
                      </div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">{formatRel(o.ts)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Follow-up History Box */}
        {em.follow_ups && em.follow_ups.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 px-1">
              <Zap className="w-4 h-4 text-amber-500 fill-amber-500" />
              <p className="text-[10px] tracking-[0.2em] uppercase font-bold text-slate-500">Automation Sequence</p>
            </div>
            <div className="space-y-3">
              {em.follow_ups.map((f, i) => (
                <div key={i} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
                  {f.sent && <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500" />}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex flex-col">
                      <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border w-fit ${f.sent ? "bg-emerald-50 text-emerald-700 border-emerald-100" : "bg-amber-50 text-amber-700 border-amber-100"}`}>
                        {f.sent ? "Successfully Sent" : "Upcoming Follow-up"}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-bold uppercase">{formatRel(f.sent_at || f.scheduled_at)}</span>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3 border border-slate-100 group-hover:bg-white transition-colors">
                    <p className="text-sm text-slate-600 leading-relaxed italic">"{f.message}"</p>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-slate-400 font-medium">
                    <span>{fmt(f.sent_at || f.scheduled_at)}</span>
                    {f.sent && <CheckCheck className="w-3 h-3 text-emerald-500" />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
