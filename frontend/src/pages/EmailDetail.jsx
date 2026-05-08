import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCheck, ArrowLeft, Trash2, Send, Zap } from "lucide-react";
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

export default function EmailDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [em, setEm] = useState(null);
  const [days, setDays] = useState(3);
  const [msg, setMsg] = useState("");
  const [mode, setMode] = useState("manual");
  const [condition, setCondition] = useState("always");
  const [open, setOpen] = useState(false);

  const load = useCallback(() => api.get(`/emails/${id}`).then(({ data }) => setEm(data)), [id]);
  useEffect(() => { load(); }, [id, load]);

  const remove = async () => {
    if (!window.confirm("Delete this tracked email?")) return;
    await api.delete(`/emails/${id}`);
    toast.success("Deleted");
    navigate("/emails");
  };

  const submit = async () => {
    await api.post("/follow-ups", {
      tracked_email_id: id,
      message: msg,
      days_delay: Number(days),
      mode,
      trigger_condition: condition,
    });
    toast.success("Follow-up scheduled");
    setOpen(false);
    setMsg("");
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
            <Button 
              onClick={async () => {
                if (!window.confirm("Send a test follow-up via Gmail API now?")) return;
                try {
                  await api.post(`/emails/${id}/test-followup`);
                  toast.success("Test sent! Check your Gmail Sent folder.");
                  load();
                } catch (e) {
                  toast.error(e.response?.data?.detail || "Test failed");
                }
              }}
              className="bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200 rounded-lg h-11 px-4 text-xs font-bold flex items-center gap-2"
            >
              <Zap className="w-4 h-4 fill-slate-400" /> Test Gmail Send
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="schedule-followup-btn" className="bg-black text-white hover:bg-slate-800 rounded-lg h-11 px-6">
                  <Send className="w-4 h-4 mr-2" /> Follow-up
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle className="text-2xl font-black tracking-tight">Schedule Follow-up</DialogTitle>
                </DialogHeader>
                <div className="space-y-6 py-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Delay</Label>
                      <div className="flex items-center gap-2">
                         <Input
                          data-testid="followup-days"
                          type="number" min="1"
                          className="h-10 rounded-lg"
                          value={days} onChange={(e) => setDays(e.target.value)}
                        />
                        <span className="text-sm font-medium text-slate-600">days</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Condition</Label>
                      <Select value={condition} onValueChange={setCondition}>
                        <SelectTrigger className="h-10 rounded-lg">
                          <SelectValue placeholder="Select condition" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="always">Always send</SelectItem>
                          <SelectItem value="if_not_opened">If not opened</SelectItem>
                          <SelectItem value="if_not_replied">If not replied</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Custom Message</Label>
                    <Textarea
                      data-testid="followup-message"
                      value={msg} onChange={(e) => setMsg(e.target.value)}
                      rows={5}
                      className="rounded-xl resize-none focus:ring-[#10B981]"
                      placeholder={`Hi ${em.recipient.split("@")[0]}, just checking in on this...`}
                    />
                  </div>

                  <div className="space-y-3">
                    <Label className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Delivery Mode</Label>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => setMode("manual")}
                        className={`p-3 text-left rounded-xl border transition-all ${mode === "manual" ? "border-black bg-black text-white shadow-md" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}
                      >
                        <div className="text-xs font-bold mb-0.5">Manual</div>
                        <div className="text-[10px] opacity-70">Reminder on dashboard</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setMode("auto")}
                        className={`p-3 text-left rounded-xl border transition-all ${mode === "auto" ? "border-black bg-black text-white shadow-md" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}
                      >
                        <div className="text-xs font-bold mb-0.5">Automatic</div>
                        <div className="text-[10px] opacity-70">Send via Gmail extension</div>
                      </button>
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={submit} className="w-full bg-[#10B981] hover:bg-emerald-600 text-white rounded-xl h-12 font-bold text-base shadow-lg shadow-emerald-200 transition-all active:scale-[0.98]">
                    Set Follow-up Schedule
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
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
