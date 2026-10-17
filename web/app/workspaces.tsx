"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BellRing, CalendarClock, Check, CheckCircle2, ClipboardCopy, Clock3,
  Download, ExternalLink, FileText, FolderSearch, LoaderCircle,
  Pencil, Plus, Radar, Search, Send, Trash2, X
} from "lucide-react";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!res.ok) {
    const parsed = await res.json().catch(() => ({}));
    throw new Error(typeof parsed.detail === "string" ? parsed.detail : "Błąd połączenia");
  }
  return res.json() as Promise<T>;
}
function displayDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" });
}
function initials(value: string) {
  return value.split(/\W+/).filter(Boolean).slice(0, 2).map(x => x[0]).join("").toUpperCase();
}
type Feedback = (message: string) => void;
type Watch = { id: number; name: string; query: string; location: string; enabled: boolean; created_at?: string };
type WatchData = Pick<Watch, "name" | "query" | "location" | "enabled">;
const emptyWatch: WatchData = { name: "", query: "", location: "", enabled: true };

export function SearchWatches({ sources, onMessage, onError }: {
  sources: string[]; onMessage: Feedback; onError: Feedback;
}) {
  const [watches, setWatches] = useState<Watch[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState<WatchData>(emptyWatch);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setWatches(await request<Watch[]>("/api/watches")); }
    catch (e) { onError((e as Error).message); }
    finally { setLoading(false); }
  }, [onError]);

  useEffect(() => { void load(); }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      await request(editing === null ? "/api/watches" : "/api/watches/" + editing, {
        method: editing === null ? "POST" : "PUT",
        body: JSON.stringify(form)
      });
      setForm(emptyWatch); setEditing(null);
      await load();
      onMessage("Wyszukiwanie zostało zapisane");
    } catch (e) { onError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function toggle(watch: Watch) {
    try {
      await request("/api/watches/" + watch.id, { method: "PUT", body: JSON.stringify({
        name: watch.name, query: watch.query, location: watch.location, enabled: !watch.enabled
      }) });
      await load();
      onMessage(!watch.enabled ? "Wyszukiwanie aktywowane" : "Wyszukiwanie wstrzymane");
    } catch (e) { onError((e as Error).message); }
  }
  async function remove(watch: Watch) {
    if (!window.confirm('Usunąć wyszukiwanie "' + watch.name + '"?')) return;
    try {
      await request("/api/watches/" + watch.id, { method: "DELETE" });
      if (editing === watch.id) { setEditing(null); setForm(emptyWatch); }
      await load(); onMessage("Wyszukiwanie usunięte");
    } catch (e) { onError((e as Error).message); }
  }
  return <div className="workspace-stack">
    <div className="heading-row"><div><div className="eyebrow"><Radar size={14}/> AUTOMATYCZNE WYSZUKIWANIE</div>
      <h1>Obserwowane wyszukiwania</h1><p>Wyszukuj kilka stanowisk jednocześnie i otrzymuj dopasowane ogłoszenia.</p>
    </div><span className="tag purple">{watches.filter(w => w.enabled).length} / 5 aktywnych</span></div>
    {!sources.includes("Adzuna") && <div className="workspace-tip"><BellRing size={19}/><div><strong>Połącz Adzuna, aby aktywować wyszukiwanie po frazach i lokalizacji.</strong><p>Dodaj ADZUNA_APP_ID i ADZUNA_APP_KEY w Dokploy. Arbeitnow, Greenhouse i Lever pozostają niezależnymi źródłami ofert.</p></div></div>}
    <div className="workspace-two-cols">
      <section className="panel ws-panel">
        <div className="panel-header"><div><h2><FolderSearch size={18}/> Twoje obserwacje</h2><p>Włączaj lub wstrzymuj poszczególne zapytania</p></div></div>
        {loading ? <div className="ws-empty"><LoaderCircle className="spin" size={22}/></div> : watches.length ? <div className="watches-list">{watches.map(watch => <div className="watch-item" key={watch.id}>
          <div className="watch-icon"><Search size={17}/></div>
          <div className="watch-info"><strong>{watch.name}</strong><span>„{watch.query}” {watch.location && "· " + watch.location}</span></div>
          <div className="watch-actions">
            <button className={"switch-button " + (watch.enabled ? "on" : "")} onClick={() => toggle(watch)} title={watch.enabled ? "Wstrzymaj" : "Aktywuj"} aria-label={watch.enabled ? "Wstrzymaj wyszukiwanie" : "Aktywuj wyszukiwanie"}><span/></button>
            <button className="icon-button" aria-label="Edytuj" title="Edytuj" onClick={() => { setEditing(watch.id); setForm({ name: watch.name, query: watch.query, location: watch.location, enabled: watch.enabled }); }}><Pencil size={15}/></button>
            <button className="icon-button" aria-label="Usuń" title="Usuń" onClick={() => void remove(watch)}><Trash2 size={15}/></button>
          </div>
        </div>)}</div> : <div className="ws-empty"><FolderSearch size={27}/><h3>Nie obserwujesz jeszcze ofert</h3><p>Dodaj wyszukiwanie, na przykład „Python Developer” w Poznaniu.</p></div>}
      </section>
      <section className="panel ws-panel">
        <div className="panel-header"><div><h2>{editing ? "Edytuj wyszukiwanie" : "Nowe wyszukiwanie"}</h2><p>Zdefiniuj stanowisko i lokalizację</p></div>{editing && <button className="icon-button" aria-label="Anuluj edycję" onClick={() => { setEditing(null); setForm(emptyWatch); }}><X size={16}/></button>}</div>
        <form className="settings-form ws-form" onSubmit={save}>
          <label>Nazwa wyszukiwania<input required maxLength={80} minLength={2} placeholder="np. Python / Automation" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label>
          <label>Stanowisko / fraza<input required maxLength={120} minLength={2} placeholder="np. Python Developer" value={form.query} onChange={e => setForm({ ...form, query: e.target.value })}/></label>
          <label>Miasto (opcjonalne)<input maxLength={100} placeholder="np. Poznań" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}/></label>
          <label className="checkbox-row"><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })}/> Aktywne wyszukiwanie</label>
          <button type="submit" className="btn primary" disabled={busy || (editing === null && watches.length >= 5)}>{busy ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>} {editing ? "Zapisz zmiany" : "Dodaj wyszukiwanie"}</button>
          <p className="ws-explainer">Maksymalnie 5 wyszukiwań. Aktualizacje ofert odbywają się cyklicznie. Osobne zapytania Adzuna zużywają limit API.</p>
        </form>
      </section>
    </div>
  </div>;
}

type PipelineStage = "draft" | "applied" | "interview" | "offer" | "rejected" | "withdrawn";
type Application = {
  id: number; job_id: string; title: string; company: string; location: string; url: string;
  score: number; status: PipelineStage; notes: string; follow_up: string | null; letter: string;
  created_at: string; updated_at: string;
};
type HistoryItem = { event: string; stage: string; created_at: string };
const stages: { value: PipelineStage; label: string; subtitle: string; tint: string }[] = [
  { value: "draft", label: "Do wysłania", subtitle: "Przygotuj i sprawdź", tint: "gray" },
  { value: "applied", label: "Wysłane", subtitle: "Potwierdzone ręcznie", tint: "violet" },
  { value: "interview", label: "Rozmowa", subtitle: "Etap rekrutacyjny", tint: "amber" },
  { value: "offer", label: "Oferta", subtitle: "Pozytywna decyzja", tint: "green" },
  { value: "rejected", label: "Odrzucone", subtitle: "Zakończone", tint: "red" },
  { value: "withdrawn", label: "Wycofane", subtitle: "Zakończone", tint: "gray" }
];

export function ApplicationBoard({ onMessage, onError, onChanged }: {
  onMessage: Feedback; onError: Feedback; onChanged: () => Promise<void>;
}) {
  const [apps, setApps] = useState<Application[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [working, setWorking] = useState<Application | null>(null);
  const [events, setEvents] = useState<HistoryItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    try {
      setApps(await request<Application[]>("/api/applications/pipeline"));
    } catch (e) { onError((e as Error).message); } finally { setLoading(false); }
  }, [onError]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const picked = apps.find(a => a.id === selected) || null;
    setWorking(picked);
    if (picked) void request<HistoryItem[]>(`/api/applications/pipeline/${picked.id}/events`).then(setEvents).catch(() => setEvents([]));
    else setEvents([]);
  }, [selected, apps]);

  async function update() {
    if (!working) return;
    setSaving(true);
    try {
      await request("/api/applications/pipeline/" + working.id, {
        method: "PATCH", body: JSON.stringify({
          status: working.status, notes: working.notes, letter: working.letter,
          follow_up: working.follow_up || null
        })
      });
      await load(); await onChanged(); onMessage("Etap i notatki zostały zapisane");
    } catch (e) { onError((e as Error).message); }
    finally { setSaving(false); }
  }
  async function remove() {
    if (!working || !window.confirm("Usunąć kartę z historii aplikacji?")) return;
    try {
      await request("/api/applications/pipeline/" + working.id, { method: "DELETE" });
      setSelected(null); await load(); await onChanged();
      onMessage("Aplikacja usunięta z pipeline");
    } catch (e) { onError((e as Error).message); }
  }
  async function copyLetter() {
    if (!working) return;
    try { await navigator.clipboard.writeText(working.letter); onMessage("Szkic skopiowany. Nic nie zostało wysłane."); }
    catch { onError("Przeglądarka zablokowała kopiowanie"); }
  }

  const shown = useMemo(() => apps.filter(a => (
    (a.title + " " + a.company).toLowerCase().includes(q.trim().toLowerCase())
  )), [apps, q]);
  return <div className="workspace-stack">
    <div className="heading-row"><div><div className="eyebrow"><Send size={14}/> APPLICATION PIPELINE</div>
      <h1>Moje aplikacje</h1><p>Przygotuj zgłoszenia, śledź rekrutacje i pilnuj kontaktu.</p>
    </div><a href="/api/applications/export.csv" className="btn secondary"><Download size={15}/> Eksport CSV</a></div>
    <div className="workspace-tip"><CheckCircle2 size={18}/><div><strong>Pełna kontrola nad zgłoszeniami</strong><p>JobPilot przygotowuje treść i otwiera ogłoszenie, ale niczego nie wysyła bez Twojego działania. Status „Wysłane” potwierdzasz ręcznie.</p></div></div>
    <div className="pipeline-toolbar"><div className="searchbox"><Search size={17}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Szukaj firmy lub stanowiska..."/></div><span>{shown.length} aplikacji</span></div>
    {loading ? <div className="ws-empty"><LoaderCircle size={24} className="spin"/></div> :
      shown.length ? <div className="pipeline-columns">{stages.map(stage => <section key={stage.value} className="pipeline-column">
        <div className="pipeline-head"><div className={"pipeline-dot " + stage.tint}/><strong>{stage.label}</strong><span>{shown.filter(a => a.status === stage.value).length}</span></div>
        <p>{stage.subtitle}</p>
        {shown.filter(a => a.status === stage.value).map(app => <button key={app.id} className={"pipeline-card " + (selected === app.id ? "active" : "")} onClick={() => setSelected(app.id)}>
          <span className="pipeline-company">{initials(app.company)}</span>
          <strong>{app.title}</strong><small>{app.company}</small><div className="pipeline-card-footer">{app.follow_up ? <span><CalendarClock size={12}/> {app.follow_up}</span> : <span><Clock3 size={12}/> {displayDate(app.created_at)}</span>}<span>{app.score}%</span></div>
        </button>)}
      </section>)}</div> : <div className="panel"><div className="ws-empty"><Send size={26}/><h3>Brak przygotowanych aplikacji</h3><p>Otwórz „Oferty pracy”, wybierz ogłoszenie i kliknij „Przygotuj aplikację”.</p></div></div>}
    {working && <div className="drawer-overlay" onClick={() => setSelected(null)}>
      <div className="app-drawer" onClick={e => e.stopPropagation()}>
        <div className="drawer-title"><div><div className="eyebrow">EDYTUJ APLIKACJĘ</div><h2>{working.title}</h2><p>{working.company} · {working.location}</p></div><button className="icon-button" onClick={() => setSelected(null)} aria-label="Zamknij"><X size={19}/></button></div>
        <div className="drawer-body">
          <label>Etap rekrutacji<select value={working.status} onChange={e => setWorking({ ...working, status: e.target.value as PipelineStage })}>{stages.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
          {working.status === "applied" && <p className="drawer-warning">Ustaw „Wysłane” tylko wtedy, gdy faktycznie złożyłeś aplikację na stronie pracodawcy.</p>}
          <label>Przypomnienie / termin kontaktu<input type="date" value={working.follow_up || ""} onChange={e => setWorking({ ...working, follow_up: e.target.value || null })}/></label>
          <label>Notatki<textarea rows={4} maxLength={4000} value={working.notes} onChange={e => setWorking({ ...working, notes: e.target.value })} placeholder="Kontakt do rekrutera, odpowiedź, ustalenia..."/></label>
          <div className="drawer-section-heading"><strong>Wiadomość rekrutacyjna</strong><button className="text-button" type="button" onClick={() => void copyLetter()}><ClipboardCopy size={14}/> Kopiuj</button></div>
          <textarea className="letter-editor" value={working.letter} maxLength={6000} onChange={e => setWorking({ ...working, letter: e.target.value })} rows={10}/>
          <p className="ws-explainer">To szkic oparty wyłącznie na Twoich danych. Zweryfikuj treść przed wysyłką.</p>
          <div className="drawer-actions"><button className="btn primary" disabled={saving} onClick={() => void update()}>{saving ? <LoaderCircle className="spin" size={15}/> : <Check size={15}/>} Zapisz zmiany</button>
            <a className="btn secondary" href={working.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/> Otwórz formularz</a></div>
          <div className="drawer-section-heading"><strong>Oś czasu</strong></div>
          <div className="history-list">{events.length ? events.map((event, i) => <div className="history-event" key={i}><span className="history-line"/><div><strong>{event.event}</strong><small>{displayDate(event.created_at)}</small></div></div>) : <p className="ws-explainer">Brak zdarzeń</p>}</div>
          <button className="text-button danger" onClick={() => void remove()}><Trash2 size={14}/> Usuń z pipeline</button>
        </div>
      </div>
    </div>}
  </div>;
}

export function CvUploader({ onImported, onMessage, onError }: {
  onImported: (text: string) => void; onMessage: Feedback; onError: Feedback;
}) {
  const [busy, setBusy] = useState(false);
  async function upload(file: File | null) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 2 * 1024 * 1024) {
      onError("Prześlij dokument PDF o rozmiarze do 2 MB"); return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/profile/cv/pdf", {
        method: "POST", headers: { "Content-Type": "application/pdf" },
        credentials: "same-origin", body: file
      });
      const result = await res.json();
      if (!res.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Błąd importu");
      onImported(result.text);
      onMessage(`Odczytano ${result.pages} stron CV. Kliknij „Zapisz zmiany”, aby zapisać tekst.`);
    } catch (err) { onError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <label className="cv-upload"><FileText size={16}/><span>{busy ? "Odczytywanie dokumentu..." : "Wczytaj CV z PDF (do 2 MB)"}</span><input
    disabled={busy} type="file" accept=".pdf,application/pdf" onChange={e => {
      const file = e.target.files?.[0] || null; e.target.value = ""; void upload(file);
    }}/></label>;
}
