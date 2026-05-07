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

export default function Emails() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [days, setDays] = useState(3);
  const [msg, setMsg] = useState("");
  const [mode, setMode] = useState("manual");
  const [condition, setCondition] = useState("always");

  const PAGE_SIZE = 15;

  const load = async () => {
    try {
      const { data } = await api.get("/emails");
      setRows(data);
    } catch (e) {
      toast.error("Failed to load emails");
    }
  };

  useEffect(() => { load(); }, []);

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

  const toggleSelect = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === paginatedRows.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(paginatedRows.map((r) => r.id));
    }
  };

  const handleBulkSubmit = async () => {
    try {
      await api.post("/follow-ups/bulk", {
        tracked_email_ids: selectedIds,
        message: msg,
        days_delay: Number(days),
        mode,
        trigger_condition: condition,
      });
      toast.success(`Follow-up scheduled`);
      setBulkOpen(false);
      setSelectedIds([]);
      setMsg("");
      load();
    } catch (e) {
      toast.error("Failed to schedule");
    }
  };

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
          {selectedIds.length > 0 && (
            <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
              <DialogTrigger asChild>
                <Button className="bg-black text-white hover:bg-slate-800 rounded px-4 h-9 text-xs font-bold shadow-sm flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 fill-yellow-400 text-yellow-400" /> Bulk Action ({selectedIds.length})
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md rounded-lg">
                <DialogHeader>
                  <DialogTitle className="text-xl font-bold">Bulk Sequence</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <Label className="text-[10px] uppercase font-bold text-slate-500">Delay (Days)</Label>
                      <Input
                        type="number" min="1"
                        className="h-9 rounded border-slate-200"
                        value={days} onChange={(e) => setDays(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] uppercase font-bold text-slate-500">Trigger</Label>
                      <Select value={condition} onValueChange={setCondition}>
                        <SelectTrigger className="h-9 rounded border-slate-200">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="always">Everyone</SelectItem>
                          <SelectItem value="if_not_opened">No Open</SelectItem>
                          <SelectItem value="if_not_replied">No Reply</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] uppercase font-bold text-slate-500">Message</Label>
                    <Textarea
                      value={msg} onChange={(e) => setMsg(e.target.value)}
                      rows={4}
                      className="rounded border-slate-200 text-sm resize-none"
                      placeholder="Hi, just checking in..."
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={handleBulkSubmit} className="w-full bg-black text-white rounded h-10 font-bold">
                    Schedule Sequence
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/50">
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded border-slate-300 text-black focus:ring-black cursor-pointer"
                    checked={selectedIds.length > 0 && selectedIds.length === paginatedRows.length}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Status</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Subject</th>
                <th className="px-4 py-3 text-[10px] uppercase font-bold text-slate-400 tracking-wider">Recipient</th>
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
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-slate-300 text-black focus:ring-black cursor-pointer"
                      checked={selectedIds.includes(e.id)}
                      onChange={() => toggleSelect(e.id)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                       {e.replied ? (
                         <div className="text-emerald-600 flex items-center gap-1 font-bold text-[10px] uppercase">
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
                  <td className="px-4 py-3 text-[11px] text-slate-400 font-medium">{fmt(e.sent_at)}</td>
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
