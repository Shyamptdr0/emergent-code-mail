import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageCircle, CheckCircle2, ArrowUpRight } from "lucide-react";
import { api } from "../lib/api";

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function ActiveMails() {
  const [data, setData] = useState({ items: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const LIMIT = 15;

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/emails/active?page=${page}&limit=${LIMIT}`);
      setData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page]);

  const rows = data.items;
  const totalPages = data.pages;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <MessageCircle className="w-6 h-6 text-emerald-500" />
          Active Mails
        </h1>
        <div className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded border border-emerald-100 uppercase tracking-widest">
          {data.total} Conversions
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
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Last Activity</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider text-right">Opens</th>
                <th className="px-4 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-4 py-12 text-center text-slate-400 text-sm italic">
                    Loading conversations...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-12 text-center text-slate-400 text-sm italic">
                    No replied emails found yet.
                  </td>
                </tr>
              ) : (
                rows.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5 text-emerald-600 font-bold text-[10px] uppercase">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Replied
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Link to={`/emails/${e.id}`} className="text-sm font-bold text-slate-900 hover:underline">{e.subject || "(No Subject)"}</Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">{e.recipient}</td>
                    <td className="px-4 py-3 text-[11px] text-slate-400 font-medium">{fmt(e.replied_at || e.last_activity_at || e.sent_at)}</td>
                    <td className="px-4 py-3 text-right text-sm font-bold text-slate-900">{e.open_count}</td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/emails/${e.id}`} className="p-1 text-slate-400 hover:text-black">
                        <ArrowUpRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                ))
              )}
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
                disabled={page === 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 border border-slate-200 rounded text-[10px] font-bold uppercase disabled:opacity-30 hover:bg-white"
              >
                Prev
              </button>
              <button
                disabled={page === totalPages || loading}
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
