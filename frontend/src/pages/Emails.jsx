import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCheck, MessageCircle, Zap, Clock } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Label } from "../components/ui/label";
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

function formatRemaining(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (d.getTime() - Date.now()) / 1000;
  if (diff < 0) return "Due now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m remain`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h remain`;
  const days = Math.floor(diff / 86400);
  if (days === 1) return "tomorrow";
  return `${days}d remain`;
}

export default function Emails() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const PAGE_SIZE = 10;

  const load = async () => {
    try {
      const { data } = await api.get("/emails");
      setRows(data);
    } catch (e) {
      toast.error("Failed to load emails");
    }
  };

  useEffect(() => { 
    load(); 
    
    // SSE for real-time updates
    const token = localStorage.getItem("token");
    if (!token) return;
    
    const backendUrl = import.meta.env.VITE_API_URL || "";
    const es = new EventSource(`${backendUrl}/api/events/stream?token=${token}`);
    
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "open" || data.type === "reply") {
        load(); // Reload data on open/reply
      }
    };
    
    return () => es.close();
  }, []);

  const filtered = rows.filter(
    (r) =>
      (r.subject || "").toLowerCase().includes(q.toLowerCase()) ||
      (r.recipient || "").toLowerCase().includes(q.toLowerCase())
  );

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE) || 1;
  const paginatedRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [q]);


  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row items-center justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Tracked emails</h1>
        
        <div className="flex items-center gap-3 w-full md:w-auto">
          <div className="relative flex-1 md:w-64">
            <input
              placeholder="Search..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="bg-white border border-slate-200 px-3 py-1.5 text-sm rounded focus:border-slate-400 w-full outline-none transition-all"
            />
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/50">
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Status</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Subject</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Recipient</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Automation</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Sent</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider text-right">Opens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-4 py-12 text-center text-slate-400 text-sm">No records found</td>
                </tr>
              )}
              {paginatedRows.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50/50 transition-colors">
                   <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                       {e.replied ? (
                         <div className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded text-[10px] font-black uppercase flex items-center gap-1 border border-emerald-200">
                           <MessageCircle className="w-3 h-3" /> Replied
                         </div>
                       ) : (
                         <CheckCheck className={`w-4 h-4 ${e.open_count > 0 ? "text-emerald-500" : "text-slate-200"}`} strokeWidth={2.5} />
                       )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/emails/${e.id}`} className="text-sm font-bold text-slate-900 hover:underline">{e.subject || "(No Subject)"}</Link>
                    {e.follow_up_count > 0 && (
                       <span className="ml-2 text-[9px] font-bold text-slate-400 uppercase tracking-tighter">+{e.follow_up_count} FUP</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-500">{e.recipient}</td>
                  <td className="px-4 py-3">
                    {e.replied ? (
                      <div className="flex flex-col">
                        <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-widest bg-emerald-50 px-2 py-1 rounded w-fit border border-emerald-100">Replied</span>
                        <span className="text-[9px] text-slate-400 font-bold mt-1">Campaign Stopped</span>
                      </div>
                    ) : e.next_followup ? (
                      <div className="flex flex-col group">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-black text-slate-900">{e.next_followup.label}</span>
                          <div className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase border ${
                            (e.next_followup.condition === "if_no_open" || e.next_followup.condition === "if_opened_no_reply") && e.open_count === 0 
                            ? "bg-slate-100 text-slate-500 border-slate-200" 
                            : "bg-amber-50 text-amber-600 border-amber-100"
                          }`}>
                            {e.next_followup.condition.replace("if_", "").replace(/_/g, " ")}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 text-slate-500">
                          <Clock className="w-3 h-3" />
                          <span className="text-[10px] font-bold uppercase tracking-tighter">
                            {formatRemaining(e.next_followup.scheduled_at)}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col opacity-30">
                         <span className="text-[10px] text-slate-400 font-bold uppercase tracking-widest italic">No Active Sequence</span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    <div className="font-bold text-slate-900">{formatRel(e.last_activity_at || e.sent_at)}</div>
                    <div>{fmt(e.last_activity_at || e.sent_at)}</div>
                  </td>
                  <td className="px-4 py-3 text-right text-sm font-bold text-slate-900">{e.open_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/30">
            <span className="text-[10px] font-bold text-slate-400 uppercase">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 border border-slate-200 rounded text-[10px] font-bold uppercase disabled:opacity-30 hover:bg-white"
              >
                Prev
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-3 py-1 border border-slate-200 rounded text-[10px] font-bold uppercase disabled:opacity-30 hover:bg-white"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
