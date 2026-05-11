import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCheck, ArrowLeft, Trash2 } from "lucide-react";
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

  if (!em) return <div className="text-slate-500 font-mono text-sm p-10">Loading…</div>;

  return (
    <div className="space-y-8" data-testid="email-detail-root">
      <button onClick={() => navigate(-1)} className="text-sm flex items-center gap-2 text-slate-600 hover:text-black" data-testid="back-btn">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="bg-white border border-slate-200 p-4 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 mb-3">
              <CheckCheck
                className={`w-6 h-6 shrink-0 ${em.open_count > 0 ? "text-[#10B981]" : "text-slate-300"}`}
                strokeWidth={2.5}
              />
              <span className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500">
                {em.open_count > 0 ? "Opened" : "Not yet opened"}
              </span>
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

      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-slate-500 mb-4">Open timeline</p>
        <div className="bg-white border border-slate-200">
          {em.opens.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-500" data-testid="opens-empty">
              No opens yet.
              {em.scan_count > 0 && (
                <div className="mt-2 text-xs text-slate-400">
                  ({em.scan_count} scan{em.scan_count > 1 ? "s" : ""} filtered — Gmail/sender pre-fetch ignored)
                </div>
              )}
            </div>
          ) : (
            em.opens.slice().reverse().map((o, i) => (
              <div key={i} className="px-6 py-4 border-b border-slate-100 last:border-0 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
                  <span className="text-sm font-medium">{fmt(o.ts)}</span>
                </div>
                <span className="text-xs font-mono text-slate-500 truncate max-w-md">{o.ua}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
