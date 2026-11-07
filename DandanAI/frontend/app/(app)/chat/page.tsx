"use client";

import { useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Send, Volume2, Plus, Sparkles, User, Bot,
  Trash2, Pencil, Check, X, BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Empty, Page, Select, Textarea, useLoad } from "@/components/ui";
import { AvatarCanvas, type AvatarCanvasHandle } from "@/components/AvatarCanvas";

/** Strip markdown and bracket labels for clean TTS voice */
function cleanForVoice(text: string): string {
  return text
    .replace(/\[(?:SYNTHETIC TEST DATA|MOCK LLM[^\]]*|outcome prediction removed[^\]]*)[^\]]*\]/gi, "")
    .replace(/\[.*?\]/g, "")           // strip any remaining bracketed tags
    .replace(/\*\*(.*?)\*\*/g, "$1")   // bold
    .replace(/\*(.*?)\*/g, "$1")       // italic
    .replace(/^#{1,6}\s+/gm, "")      // headings
    .replace(/^•\s*/gm, "")           // bullets
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export default function Chat() {
  const { toast } = useAuth();
  const convs = useLoad<any[]>("/api/v1/chat/conversations");
  const cases = useLoad<any[]>("/api/v1/cases");

  const [cid, setCid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"text" | "voice">("voice");
  const [busy, setBusy] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [transcribed, setTranscribed] = useState(false);
  const [recording, setRecording] = useState(false);
  // Voice summary toggle: true = avatar speaks only summary; false = full response
  const [voiceSummary, setVoiceSummary] = useState(true);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");

  const avatarRef = useRef<AvatarCanvasHandle | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const speechRecRef = useRef<any>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const open = async (id: string) => {
    avatarRef.current?.stopSpeaking();
    setCid(id);
    setMsgs(await api(`/api/v1/chat/conversations/${id}/messages`));
  };

  const newConv = async () => {
    avatarRef.current?.stopSpeaking();
    const c = await api("/api/v1/chat/conversations", { body: { case_id: caseId || null } });
    await convs.reload();
    await open(c.id);
  };

  // ── Delete conversation ─────────────────────────────────────────────────────
  const deleteConv = async (id: string) => {
    if (!confirm("Delete this conversation? This cannot be undone.")) return;
    try {
      await api(`/api/v1/chat/conversations/${id}`, { method: "DELETE" });
      if (cid === id) { setCid(null); setMsgs([]); avatarRef.current?.stopSpeaking(); }
      await convs.reload();
    } catch (e: any) {
      toast(e.message || "Failed to delete conversation", "err");
    }
  };

  // ── Rename conversation ─────────────────────────────────────────────────────
  const startRename = (id: string, currentTitle: string) => {
    setRenamingId(id); setRenameVal(currentTitle);
  };
  const confirmRename = async (id: string) => {
    const title = renameVal.trim();
    if (!title) return cancelRename();
    try {
      await api(`/api/v1/chat/conversations/${id}`, { method: "PATCH", body: { title } });
      await convs.reload();
    } catch (e: any) { toast(e.message || "Failed to rename conversation", "err"); }
    cancelRename();
  };
  const cancelRename = () => { setRenamingId(null); setRenameVal(""); };

  // ── TTS / Avatar speak ──────────────────────────────────────────────────────
  const speak = async (rawText: string) => {
    const t = cleanForVoice(rawText);
    if (!t) return;
    try {
      avatarRef.current?.stopSpeaking();
      const r: Response = await api("/api/v1/voice/tts", {
        body: { text: t.slice(0, 1000) },
        raw: true,
      });
      const blob = await r.blob();
      if (avatarRef.current) {
        await avatarRef.current.playAudioBlob(blob);
      } else {
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        audio.onended = () => URL.revokeObjectURL(audioUrl);
        await audio.play().catch(() => toast("Autoplay blocked — click speaker icon to hear reply", "err"));
      }
    } catch (e: any) { toast(e.message || "Failed to generate voice", "err"); }
  };

  /** Pick what the avatar speaks based on the voiceSummary toggle */
  const speakMessage = (m: any) => {
    if (voiceSummary && m.meta?.voice_summary) {
      speak(m.meta.voice_summary);
    } else {
      speak(m.meta?.voice_full || m.content);
    }
  };

  const handleTestVoice = () => {
    speak("Hello! I am your AI assistant powered by Microsoft Edge TTS with Liam Canada male voice. My mouth moves naturally while speaking and stays completely motionless when silent.");
  };

  // ── Send message ────────────────────────────────────────────────────────────
  const send = async () => {
    if (!text.trim()) return;
    if (recording) stopRecording();
    avatarRef.current?.stopSpeaking();

    setBusy(true);
    const outgoingText = text;
    try {
      let id = cid;
      if (!id) {
        const c = await api("/api/v1/chat/conversations", { body: { case_id: caseId || null } });
        id = c.id; setCid(id);
      }
      const m = await api(`/api/v1/chat/conversations/${id}/messages`, {
        body: { content: outgoingText, modality: transcribed ? "voice" : "text" },
      });
      setMsgs(await api(`/api/v1/chat/conversations/${id}/messages`));
      setText(""); setTranscribed(false);
      convs.reload();

      if (mode === "voice" && m.content) {
        speakMessage(m);
      }
    } catch (e: any) { toast(e.message, "err"); }
    setBusy(false);
  };

  // ── Recording ───────────────────────────────────────────────────────────────
  const stopRecording = () => {
    if (speechRecRef.current) { try { speechRecRef.current.stop(); } catch {} speechRecRef.current = null; }
    if (rec.current && rec.current.state === "recording") { try { rec.current.stop(); } catch {} }
    setRecording(false);
  };

  const toggleRec = async () => {
    if (recording) { stopRecording(); toast("Recording ended. Edit your prompt if desired, then click Send."); return; }

    const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true; recognition.interimResults = true; recognition.lang = "en-US";
        const basePrefix = text.trim() ? text.trim() + " " : "";
        recognition.onresult = (event: any) => {
          let acc = "";
          for (let i = 0; i < event.results.length; i++) acc += event.results[i][0].transcript;
          if (acc) { setText(basePrefix + acc); setTranscribed(true); }
        };
        recognition.onerror = (e: any) => console.warn("SR notice:", e.error);
        recognition.onend = () => setRecording(false);
        recognition.start();
        speechRecRef.current = recognition;
        setRecording(true);
        toast("🎙️ Listening… Text appears live for you to review and edit.");
        return;
      } catch (err) { console.warn("Falling back to MediaRecorder", err); }
    }

    // MediaRecorder fallback
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop()); setRecording(false);
        const f = new FormData();
        f.append("file", new Blob(chunks, { type: "audio/webm" }), "voice.webm");
        try {
          const t = await api("/api/v1/voice/transcribe", { form: f });
          if (t?.transcript?.trim()) {
            setText((prev) => (prev ? prev + " " + t.transcript : t.transcript));
            setTranscribed(true);
            toast("Transcript ready — edit any words you want, then click Send.");
          } else { toast("Could not recognize speech. Please type or try again.", "err"); }
        } catch (e: any) { toast(e.message, "err"); }
      };
      r.start(); rec.current = r; setRecording(true);
      toast("🎙️ Recording audio… click Stop when finished to transcribe.");
    } catch { toast("Microphone unavailable — please check permissions or type below", "err"); }
  };

  return (
    <Page
      title="AI Legal Chat"
      subtitle="Grounded in your legal knowledge base & case files • Voice with Edge TTS Liam & 3D Avatar lip sync"
      actions={
        <div className="flex items-center gap-2">
          <Badge tone="blue">Edge TTS: Liam (Canada)</Badge>
          <Badge tone="green">3D Head Lip-Sync</Badge>
        </div>
      }
    >
      <div className="grid gap-4 lg:grid-cols-4">
        {/* Left column: Conversations */}
        <Card
          title="Conversations"
          actions={
            <Button variant="ghost" onClick={newConv} aria-label="New conversation">
              <Plus className="h-4 w-4" />
            </Button>
          }
          className="lg:col-span-1"
        >
          <Select className="mb-2" aria-label="Attach case" value={caseId} onChange={(e: any) => setCaseId(e.target.value)}>
            <option value="">No case attached</option>
            {cases.data?.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </Select>

          {!convs.data?.length ? (
            <Empty title="No conversations" />
          ) : (
            <div className="max-h-96 space-y-1 overflow-y-auto">
              {convs.data.map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-center gap-1 rounded px-2 py-1.5 text-sm ${cid === c.id ? "bg-brand-50" : "hover:bg-ink-50"}`}
                >
                  {renamingId === c.id ? (
                    <div className="flex flex-1 items-center gap-1">
                      <input
                        autoFocus
                        className="flex-1 min-w-0 rounded border border-brand-300 px-1 py-0.5 text-xs outline-none focus:ring-1 focus:ring-brand-400"
                        value={renameVal}
                        onChange={(e) => setRenameVal(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") confirmRename(c.id); if (e.key === "Escape") cancelRename(); }}
                      />
                      <button onClick={() => confirmRename(c.id)} className="text-emerald-600 hover:text-emerald-800" title="Save"><Check className="h-3.5 w-3.5" /></button>
                      <button onClick={cancelRename} className="text-ink-400 hover:text-ink-700" title="Cancel"><X className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <>
                      <button onClick={() => open(c.id)} className={`flex-1 truncate text-left text-sm ${cid === c.id ? "font-medium text-brand-900" : ""}`}>
                        {c.title}
                      </button>
                      <button onClick={() => startRename(c.id, c.title)} className="hidden group-hover:inline-flex text-ink-400 hover:text-brand-600" title="Rename"><Pencil className="h-3 w-3" /></button>
                      <button onClick={() => deleteConv(c.id)} className="hidden group-hover:inline-flex text-ink-400 hover:text-red-600" title="Delete"><Trash2 className="h-3 w-3" /></button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Right column: Chat & Avatar */}
        <Card
          className="lg:col-span-3"
          title="AI Conversation"
          actions={
            <div className="flex items-center gap-1.5">
              <Button variant={mode === "text" ? "primary" : "outline"} size="sm" onClick={() => setMode("text")}>Text</Button>
              <Button variant={mode === "voice" ? "primary" : "outline"} size="sm" onClick={() => setMode("voice")}>
                <Sparkles className="mr-1 h-3.5 w-3.5" />Voice & Avatar
              </Button>
              {/* Voice summary toggle */}
              {mode === "voice" && (
                <button
                  type="button"
                  onClick={() => setVoiceSummary((v) => !v)}
                  title={voiceSummary ? "Avatar speaks summary only — click for full response" : "Avatar speaks full response — click for summary only"}
                  className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                    voiceSummary
                      ? "border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                      : "border-ink-200 bg-ink-50 text-ink-500 hover:bg-ink-100"
                  }`}
                >
                  <BookOpen className="h-3 w-3" />
                  {voiceSummary ? "Voice: Summary" : "Voice: Full"}
                </button>
              )}
            </div>
          }
        >
          {/* Avatar Section */}
          {mode === "voice" && (
            <div className="mb-4">
              <AvatarCanvas ref={avatarRef} onTestVoice={handleTestVoice} />
            </div>
          )}

          {/* Messages stream */}
          <div className="mb-3 h-80 space-y-3 overflow-y-auto rounded-lg border border-ink-100 bg-ink-50/30 p-3 sm:h-96" aria-live="polite">
            {!msgs.length ? (
              <Empty title="Ask a question or record speech">
                e.g. "What documents do I need to file a case for a water pipe leak complaint?"
              </Empty>
            ) : (
              msgs.map((m) => (
                <div
                  key={m.id}
                  className={`flex flex-col max-w-[85%] rounded-xl p-3.5 text-sm shadow-sm ${
                    m.role === "user" ? "ml-auto bg-brand-600 text-white" : "mr-auto border border-ink-200 bg-white text-ink-900"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-1.5 text-xs opacity-75">
                    {m.role === "user" ? (
                      <><User className="h-3 w-3" /><span>You</span>{m.modality === "voice" && <Badge tone="blue">Voice input</Badge>}</>
                    ) : (
                      <><Bot className="h-3 w-3 text-brand-600" /><span className="font-medium text-brand-700">DandanAI Assistant</span></>
                    )}
                  </div>

                  <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>

                  {m.role === "assistant" && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-ink-100 pt-2 text-xs">
                      {m.meta?.mode && <Badge tone="amber">{m.meta?.mode} mode</Badge>}
                      {m.meta?.confidence && <Badge tone="green">support: {m.meta?.confidence}</Badge>}
                      {m.citations?.map((c: any) => (
                        <Badge key={c.chunk_id} tone="blue">{c.pinpoint}</Badge>
                      ))}
                      {/* Play Summary button */}
                      {m.meta?.voice_summary && (
                        <button
                          type="button"
                          onClick={() => speak(m.meta.voice_summary)}
                          className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-emerald-700 hover:bg-emerald-100 transition"
                          title="Speak summary only"
                        >
                          <BookOpen className="h-3.5 w-3.5" />
                          <span>Summary</span>
                        </button>
                      )}
                      {/* Play Full button */}
                      <button
                        type="button"
                        onClick={() => speak(m.meta?.voice_full || m.content)}
                        className="ml-auto inline-flex items-center gap-1 rounded bg-brand-50 px-2 py-0.5 text-brand-700 hover:bg-brand-100 transition"
                        title="Speak full response"
                      >
                        <Volume2 className="h-3.5 w-3.5" />
                        <span>Full (Voice)</span>
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={end} />
          </div>

          {/* Voice status banner */}
          {recording && (
            <div className="mb-2 flex items-center justify-between rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700 animate-pulse">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-red-600 animate-ping" />
                <span className="font-medium">Recording… words appear in the input box below.</span>
              </div>
              <Button variant="danger" size="sm" className="!px-2 !py-0.5 text-xs" onClick={stopRecording}>
                <MicOff className="mr-1 h-3 w-3" /> Stop
              </Button>
            </div>
          )}

          {transcribed && !recording && (
            <div className="mb-2 flex items-center justify-between rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-1.5 text-xs text-emerald-800">
              <span>✏️ <strong>Transcript captured:</strong> Review or edit the text below, then click Send.</span>
              <button type="button" className="text-xs text-emerald-700 hover:underline" onClick={() => { setText(""); setTranscribed(false); }}>Clear</button>
            </div>
          )}

          {/* Input Box & Action Buttons */}
          <div className="flex gap-2">
            <Textarea
              className="!min-h-[50px] resize-y"
              aria-label="Message"
              value={text}
              onChange={(e: any) => setText(e.target.value)}
              placeholder={
                recording ? "Listening to your voice… (speak clearly)"
                : transcribed ? "Transcript loaded! Edit if needed, then click Send…"
                : "Type your legal question or click Record to speak…"
              }
              onKeyDown={(e: any) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            />
            <div className="flex flex-col gap-1.5 shrink-0">
              <Button onClick={send} loading={busy} disabled={!text.trim() || busy} aria-label="Send" className="h-9 px-3" title="Send question">
                <Send className="h-4 w-4" />
              </Button>
              <Button
                variant={recording ? "danger" : "outline"} onClick={toggleRec}
                aria-label={recording ? "Stop recording" : "Record voice"}
                className={`h-9 px-3 ${recording ? "animate-pulse" : ""}`}
                title={recording ? "Click to stop recording" : "Click to record voice"}
              >
                {recording ? <MicOff className="h-4 w-4 text-white" /> : <Mic className="h-4 w-4 text-brand-600" />}
              </Button>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between text-xs text-ink-500">
            <span>Voice answers spoken with <strong>Edge TTS Liam (Canada)</strong> male voice • {voiceSummary && mode === "voice" ? "🔖 Auto-speaking summary" : mode === "voice" ? "📄 Auto-speaking full response" : ""}</span>
            {text.trim() && <span className="text-brand-600">Press Enter to send or edit text directly.</span>}
          </div>
        </Card>
      </div>
    </Page>
  );
}
