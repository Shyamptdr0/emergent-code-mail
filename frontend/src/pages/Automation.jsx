import { useEffect, useState } from "react";
import { Zap, Clock, Trash2, Plus, Calendar, Layers, Edit2, ChevronUp, ChevronDown } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Automation() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);

  const [newRule, setNewRule] = useState({
    name: "",
    stages: [
      { trigger: "no_open", delay_value: 1, delay_unit: "days", time: "", message: "" }
    ]
  });

  const addStage = () => {
    setNewRule({
      ...newRule,
      stages: [...newRule.stages, { trigger: "no_open", delay_value: 3, delay_unit: "days", time: "", message: "" }]
    });
  };

  const removeStage = (index) => {
    if (newRule.stages.length === 1) return;
    const s = [...newRule.stages];
    s.splice(index, 1);
    setNewRule({ ...newRule, stages: s });
  };

  const moveStage = (index, dir) => {
    const s = [...newRule.stages];
    const target = index + dir;
    if (target < 0 || target >= s.length) return;
    [s[index], s[target]] = [s[target], s[index]];
    setNewRule({ ...newRule, stages: s });
  };

  const updateStage = (index, field, value) => {
    const s = [...newRule.stages];
    s[index][field] = value;
    setNewRule({ ...newRule, stages: s });
  };

  const load = async () => {
    try {
      const { data } = await api.get("/automation-rules");
      setRules(data);
    } catch (e) {
      toast.error("Failed to load automation rules");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const saveRule = async () => {
    if (!newRule.name || newRule.stages.some(s => !s.message)) {
      return toast.error("Please fill in all fields");
    }
    try {
      if (editingId) {
        await api.put(`/automation-rules/${editingId}`, newRule);
        toast.success("Updated");
      } else {
        await api.post("/automation-rules", newRule);
        toast.success("Activated");
      }
      handleCancel();
      load();
    } catch (e) {
      toast.error("Failed to save");
    }
  };

  const deleteRule = async (id) => {
    if (!window.confirm("Delete this sequence?")) return;
    try {
      await api.delete(`/automation-rules/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error("Failed to delete");
    }
  };

  const handleEdit = (rule) => {
    setNewRule({
      name: rule.name,
      repeat_last: rule.repeat_last || false,
      stages: rule.stages.map(s => ({ ...s }))
    });
    setEditingId(rule.id);
    setShowAdd(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCancel = () => {
    setShowAdd(false);
    setEditingId(null);
    setNewRule({ name: "", repeat_last: false, stages: [{ trigger: "no_open", delay_value: 1, delay_unit: "days", time: "", message: "" }] });
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-500 fill-yellow-500/10" />
            Automation
          </h1>
          <p className="text-slate-500 text-sm">Manage your multi-stage follow-up campaigns.</p>
        </div>
        <Button 
          onClick={() => showAdd ? handleCancel() : setShowAdd(true)} 
          className={`rounded h-9 px-4 text-xs font-bold transition-all ${showAdd ? "bg-slate-100 text-slate-900 hover:bg-slate-200" : "bg-black text-white hover:bg-slate-800"}`}
        >
          {showAdd ? "Cancel" : <><Plus className="w-4 h-4 mr-1.5" /> New Campaign</>}
        </Button>
      </div>

      {showAdd && (
        <div className="bg-white border border-slate-200 rounded shadow-sm overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50/30">
            <div className="flex-1 max-w-md">
              <Label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 block">Campaign Name</Label>
              <Input 
                placeholder="e.g. Sales Outreach" 
                value={newRule.name}
                onChange={e => setNewRule({...newRule, name: e.target.value})}
                className="h-9 rounded border-slate-200 font-bold text-sm"
              />
            </div>
            <div className="flex items-center gap-2 px-4 border-l border-slate-100 ml-4">
              <input 
                type="checkbox" 
                id="repeat_last"
                checked={newRule.repeat_last || false}
                onChange={e => setNewRule({...newRule, repeat_last: e.target.checked})}
                className="w-4 h-4 rounded border-slate-300 text-black focus:ring-black"
              />
              <Label htmlFor="repeat_last" className="text-[10px] font-bold uppercase tracking-wider text-slate-500 cursor-pointer">Repeat Sequence</Label>
            </div>
            {editingId && <span className="text-[10px] font-bold uppercase text-emerald-600 bg-emerald-50 px-2 py-1 rounded border border-emerald-100">Editing Mode</span>}
          </div>

          <div className="p-6 space-y-8">
            {newRule.stages.map((stage, idx) => (
              <div key={idx} className="relative pl-8 border-l-2 border-slate-100 ml-4">
                <div className="absolute -left-[11px] top-0 w-5 h-5 bg-black text-white rounded-full flex items-center justify-center text-[10px] font-bold">
                  {idx + 1}
                </div>
                
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">Step {idx + 1}</h3>
                      <div className="flex items-center gap-1">
                        <button onClick={() => moveStage(idx, -1)} disabled={idx === 0} className="p-1 text-slate-300 hover:text-black disabled:opacity-30">
                          <ChevronUp className="w-4 h-4" />
                        </button>
                        <button onClick={() => moveStage(idx, 1)} disabled={idx === newRule.stages.length - 1} className="p-1 text-slate-300 hover:text-black disabled:opacity-30">
                          <ChevronDown className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                    {newRule.stages.length > 1 && (
                      <button onClick={() => removeStage(idx)} className="text-slate-300 hover:text-red-500 transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  <div className="bg-slate-50/50 border border-slate-100 rounded p-4 space-y-4">
                    <div className="flex flex-wrap items-center gap-4 text-[11px] font-bold text-slate-700">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">IF</span>
                        <Select value={stage.trigger} onValueChange={v => updateStage(idx, "trigger", v)}>
                          <SelectTrigger className="w-40 h-8 rounded border-slate-200 bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="no_open">Not Open</SelectItem>
                            <SelectItem value="opened_no_reply">Open but No Reply</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">AFTER</span>
                        <Input 
                          type="number" 
                          value={stage.delay_value || stage.days || 1}
                          onChange={e => updateStage(idx, "delay_value", Number(e.target.value))}
                          className="w-14 h-8 text-center rounded border-slate-200 bg-white font-bold"
                        />
                        <Select value={stage.delay_unit || "days"} onValueChange={v => updateStage(idx, "delay_unit", v)}>
                          <SelectTrigger className="w-20 h-8 rounded border-slate-200 bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="hours">Hours</SelectItem>
                            <SelectItem value="days">Days</SelectItem>
                          </SelectContent>
                        </Select>
                        {(stage.delay_unit || "days") === "days" && (
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400 ml-1">AT</span>
                            <Input 
                              type="time" 
                              value={stage.time}
                              onChange={e => updateStage(idx, "time", e.target.value)}
                              className="w-28 h-8 rounded border-slate-200 bg-white font-bold"
                            />
                            {!stage.time && <span className="text-[9px] text-emerald-600 font-bold italic">(Original)</span>}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Message</Label>
                      <Textarea 
                        value={stage.message}
                        onChange={e => updateStage(idx, "message", e.target.value)}
                        rows={3}
                        className="rounded border-slate-200 bg-white p-3 text-sm text-slate-700 leading-relaxed resize-none focus:border-black"
                        placeholder="Write message..."
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}

            <button 
              onClick={addStage}
              className="ml-4 w-full py-3 border border-dashed border-slate-200 rounded text-slate-400 text-[10px] font-bold hover:border-slate-400 hover:text-slate-600 transition-all flex items-center justify-center gap-2"
            >
              <Plus className="w-3.5 h-3.5" /> Add Step
            </button>
          </div>

          <div className="p-4 bg-slate-50/50 flex justify-end gap-3 border-t border-slate-100">
            <Button variant="ghost" onClick={handleCancel} className="h-9 px-4 text-[11px] font-bold text-slate-500">Cancel</Button>
            <Button onClick={saveRule} className="bg-black text-white rounded h-9 px-6 font-bold text-[11px] shadow-sm active:scale-95">
              {editingId ? "Save Changes" : "Launch Campaign"}
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="bg-white border border-slate-200 rounded p-20 flex flex-col items-center justify-center">
          <div className="loader mb-4" />
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest animate-pulse">Loading Campaigns...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rules.length === 0 && (
            <div className="col-span-full bg-white border border-slate-200 rounded p-12 text-center">
              <Calendar className="w-8 h-8 text-slate-100 mx-auto mb-3" />
              <p className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">No active campaigns</p>
            </div>
          )}

        {rules.map((rule) => (
          <div key={rule.id} className="bg-white border border-slate-200 rounded p-5 hover:border-slate-400 transition-all group relative shadow-sm">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">{rule.name}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[9px] font-bold text-slate-400 flex items-center gap-1 uppercase">
                    <Layers className="w-3 h-3" /> {rule.stages.length} Steps
                  </span>
                  <div className="w-1 h-1 rounded-full bg-emerald-500" />
                  <span className="text-[9px] font-bold text-emerald-600 uppercase">Running</span>
                </div>
              </div>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                  onClick={() => handleEdit(rule)}
                  className="p-1.5 text-slate-400 hover:text-black hover:bg-slate-50 rounded transition-all"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
                <button 
                  onClick={() => deleteRule(rule.id)}
                  className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            
            <div className="space-y-2">
              {rule.stages.slice(0, 2).map((stage, sidx) => (
                <div key={sidx} className="bg-slate-50/50 rounded p-2 border border-slate-50 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[8px] font-bold uppercase text-slate-300">S{sidx+1}</span>
                    <span className="text-[10px] font-bold text-slate-600">
                      {stage.delay_value || stage.days || 1}{stage.delay_unit === "hours" ? "h" : "d"} @ {stage.time || "Original Time"}
                    </span>
                  </div>
                  <span className="text-[9px] text-slate-400 truncate max-w-[120px] italic">"{stage.message}"</span>
                </div>
              ))}
              {rule.stages.length > 2 && (
                <div className="text-[9px] text-center text-slate-300 font-bold uppercase tracking-tighter">
                  + {rule.stages.length - 2} more steps
                </div>
              )}
            </div>
          </div>
        ))}
        </div>
      )}
    </div>
  );
}
