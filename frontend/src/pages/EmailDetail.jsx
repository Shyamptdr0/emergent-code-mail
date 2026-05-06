import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCheck, ArrowLeft, Trash2, Send } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function EmailDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [em, setEm] = useState(null);
  const [days, setDays] = useState(3);
  const [msg, setMsg] = useState("");
  const [mode, setMode] = useState("manual");
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
    });
    toast.success("Follow-up scheduled");
    setOpen(false);
    setMsg("");
  };

  if (!em) return <div className="text-slate-500 font-mono text-sm">Loading…</div>;

  return (
    <div className="space-y-8" data-testid="email-detail-root">
      <button onClick={() => navigate(-1)} className="text-sm flex items-center gap-2 text-slate-600 hover:text-black" data-testid="back-btn">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="bg-white border border-slate-200 p-8">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-3">
              <CheckCheck
                className={`w-6 h-6 shrink-0 ${em.open_count > 0 ? "text-[#10B981]" : "text-slate-300"}`}
                strokeWidth={2.5}
              />
              <span className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500">
                {em.open_count > 0 ? "Opened" : "Not yet opened"}
              </span>
            </div>
            <h1 className="text-3xl tracking-tighter font-black break-words">{em.subject || "(no subject)"}</h1>
            <p className="text-sm font-mono text-slate-600 mt-2">to {em.recipient}</p>
            <p className="text-xs text-slate-500 mt-1">Sent {fmt(em.sent_at)}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="schedule-followup-btn" className="bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm">
                  <Send className="w-4 h-4 mr-2" /> Follow-up
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Schedule a follow-up</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Send after (days)</Label>
                    <Input
                      data-testid="followup-days"
                      type="number" min="1"
                      value={days} onChange={(e) => setDays(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Message</Label>
                    <Textarea
                      data-testid="followup-message"
                      value={msg} onChange={(e) => setMsg(e.target.value)}
                      rows={6}
                      placeholder={`Hi ${em.recipient.split("@")[0]}, just bumping this up…`}
                    />
                  </div>
                  <div>
                    <Label>Mode</Label>
                    <div className="flex gap-3 mt-2">
                      <button
                        type="button"
                        data-testid="mode-manual"
                        onClick={() => setMode("manual")}
                        className={`px-4 py-2 text-sm border ${mode === "manual" ? "bg-[#0A0A0A] text-white border-black" : "bg-white text-slate-700 border-slate-300"}`}
                      >Manual reminder</button>
                      <button
                        type="button"
                        data-testid="mode-auto"
                        onClick={() => setMode("auto")}
                        className={`px-4 py-2 text-sm border ${mode === "auto" ? "bg-[#0A0A0A] text-white border-black" : "bg-white text-slate-700 border-slate-300"}`}
                      >Auto-send via Gmail</button>
                    </div>
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                      Auto-send: extension drafts &amp; sends from your Gmail when due. Manual: dashboard shows reminder.
                    </p>
                  </div>
                </div>
                <DialogFooter>
                  <Button data-testid="followup-submit" onClick={submit} className="bg-[#10B981] hover:bg-emerald-600 rounded-sm">
                    Schedule
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
