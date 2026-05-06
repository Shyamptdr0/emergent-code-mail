import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCheck } from "lucide-react";
import { api } from "../lib/api";

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function Emails() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get("/emails").then(({ data }) => setRows(data));
  }, []);

  const filtered = rows.filter(
    (r) =>
      (r.subject || "").toLowerCase().includes(q.toLowerCase()) ||
      (r.recipient || "").toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div data-testid="emails-page">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-4xl tracking-tighter font-black">Tracked emails</h1>
        <input
          data-testid="emails-search"
          placeholder="Search…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="bg-white border border-slate-300 px-4 py-2 text-sm rounded-sm focus:ring-1 focus:ring-black focus:border-black w-72"
        />
      </div>
      <div className="bg-white border border-slate-200 overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="px-6 py-3 text-xs tracking-[0.2em] uppercase font-bold text-slate-500">Status</th>
              <th className="px-6 py-3 text-xs tracking-[0.2em] uppercase font-bold text-slate-500">Subject</th>
              <th className="px-6 py-3 text-xs tracking-[0.2em] uppercase font-bold text-slate-500">Recipient</th>
              <th className="px-6 py-3 text-xs tracking-[0.2em] uppercase font-bold text-slate-500">Sent</th>
              <th className="px-6 py-3 text-xs tracking-[0.2em] uppercase font-bold text-slate-500 text-right">Opens</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan="5" className="px-6 py-10 text-center text-sm text-slate-500" data-testid="emails-empty">
                  No emails yet.
                </td>
              </tr>
            )}
            {filtered.map((e) => (
              <tr key={e.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`email-tr-${e.id}`}>
                <td className="px-6 py-4">
                  <CheckCheck
                    className={`w-5 h-5 ${e.open_count > 0 ? "text-[#10B981]" : "text-slate-300"}`}
                    strokeWidth={2.5}
                  />
                </td>
                <td className="px-6 py-4 text-sm font-medium">
                  <Link to={`/emails/${e.id}`} className="hover:underline" data-testid={`email-link-${e.id}`}>
                    {e.subject || "(no subject)"}
                  </Link>
                </td>
                <td className="px-6 py-4 text-sm font-mono text-slate-600">{e.recipient}</td>
                <td className="px-6 py-4 text-sm text-slate-500">{fmt(e.sent_at)}</td>
                <td className="px-6 py-4 text-sm text-right font-medium">{e.open_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
