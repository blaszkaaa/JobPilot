"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BriefcaseBusiness, Check, CircleHelp, Database, ExternalLink, Globe2,
  LoaderCircle, Plus, RefreshCcw, ServerCog, ShieldCheck, Trash2, X
} from "lucide-react";

type Board = { id: number | null; provider: "greenhouse" | "lever"; slug: string; label: string; enabled: boolean; managed: boolean };
type Sources = { boards: Board[]; providers: { arbeitnow: boolean; adzuna: boolean }; limits: { max_managed: number; max_per_provider_fetch: number } };
type ManualForm = { title: string; company: string; location: string; description: string; url: string; remote: boolean };
const emptyForm: ManualForm = { title: "", company: "", location: "", description: "", url: "", remote: false };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, ...init
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw new Error(typeof json.detail === "string" ? json.detail : "Nie udało się zapisać");
  }
  return res.json() as Promise<T>;
}
type Props = { onMessage: (s: string) => void; onError: (s: string) => void; onChanged: () => Promise<void> };
export function SourcesWorkspace({ onMessage, onError, onChanged }: Props) {
  const [sources, setSources] = useState<Sources | null>(null);
  const [provider, setProvider] = useState<"greenhouse" | "lever">("greenhouse");
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try { setSources(await request<Sources>("/api/sources")); }
    catch (err) { onError((err as Error).message); }
  }, [onError]);
  useEffect(() => { void load(); }, [load]);
  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("add");
    try {
      await request("/api/sources", { method: "POST", body: JSON.stringify({ provider, slug, label }) });
      setSlug(""); setLabel("");
      await load(); await onChanged();
      onMessage("Źródło zapisane. Oferty pojawią się po kolejnym skanowaniu.");
    } catch (err) { onError((err as Error).message); }
    finally { setBusy(""); }
  }
  async function toggle(row: Board) {
    if (row.id === null) return;
    setBusy("toggle:" + row.id);
    try {
      await request("/api/sources/" + row.id, { method: "PATCH", body: JSON.stringify({ enabled: !row.enabled }) });
      await load(); await onChanged();
      onMessage(row.enabled ? "Wstrzymano źródło" : "Źródło aktywowane");
    } catch (err) { onError((err as Error).message); }
    finally { setBusy(""); }
  }
  async function remove(row: Board) {
    if (row.id === null || !window.confirm("Usunąć źródło " + row.label + "?")) return;
    setBusy("delete:" + row.id);
    try {
      await request("/api/sources/" + row.id, { method: "DELETE" });
      await load(); await onChanged(); onMessage("Źródło usunięte");
    } catch (err) { onError((err as Error).message); }
    finally { setBusy(""); }
  }
  const managed = sources?.boards.filter(x => x.managed).length ?? 0;
  return <div className="sources-workspace">
    <div className="heading-row">
      <div><div className="eyebrow"><Database size={14}/> INTEGRACJE JOBPILOT</div><h1>Źródła ofert pracy</h1>
        <p>Połącz publiczne tablice rekrutacyjne firm bez edytowania plików na serwerze.</p></div>
      <span className="tag purple">{managed} / {sources?.limits.max_managed ?? 20} dodanych</span>
    </div>
    <div className="sources-stats">
      <div className="sources-overview-card"><div className="sources-card-icon"><Globe2 size={19}/></div><div><strong>Arbeitnow</strong><span>Domyślne, publiczne API</span></div><span className="tag green">Skonfigurowane</span></div>
      <div className="sources-overview-card"><div className="sources-card-icon"><Database size={19}/></div><div><strong>Adzuna Polska</strong><span>Wyszukiwania według fraz</span></div><span className={"tag " + (sources?.providers.adzuna ? "green" : "")}>{sources?.providers.adzuna ? "Skonfigurowane" : "Wymaga kluczy"}</span></div>
    </div>
    <div className="sources-columns">
      <section className="panel">
        <div className="panel-header"><div><h2><ServerCog size={18}/> Tablice pracodawców</h2><p>Źródła pobierane podczas każdego skanowania</p></div></div>
        {sources ? sources.boards.length ? <div className="sources-list">{sources.boards.map(row => <div key={row.provider + row.slug} className="sources-list-row">
          <div className="sources-logo">{row.provider === "greenhouse" ? "GH" : "LV"}</div>
          <div className="sources-row-text"><strong>{row.label}</strong><span>{row.provider === "greenhouse" ? "Greenhouse" : "Lever"} · {row.slug}</span></div>
          <div className="sources-row-actions"><span className={"tag " + (row.enabled ? "green" : "")}>{row.enabled ? "Aktywne" : "Wstrzymane"}</span>
            {row.managed && <><button className="btn secondary" disabled={!!busy} onClick={() => void toggle(row)}>{row.enabled ? "Wstrzymaj" : "Włącz"}</button>
              <button className="icon-button" disabled={!!busy} onClick={() => void remove(row)} aria-label={"Usuń " + row.label}><Trash2 size={16}/></button></>}
            {!row.managed && <span className="sources-managed-note">Z Dokploy</span>}
          </div>
        </div>)}</div> : <div className="sources-empty"><Database size={25}/><strong>Brak dodanych tablic</strong><p>Dodaj Greenhouse lub Lever po prawej stronie.</p></div> :
          <div className="sources-empty"><LoaderCircle size={21} className="spin"/></div>}
      </section>
      <section className="panel">
        <div className="panel-header"><div><h2><Plus size={18}/> Dodaj pracodawcę</h2><p>Publiczne API Greenhouse albo Lever</p></div></div>
        <form className="settings-form source-form" onSubmit={add}>
          <label>Dostawca
            <select value={provider} onChange={e => setProvider(e.target.value as "greenhouse" | "lever")}>
              <option value="greenhouse">Greenhouse</option><option value="lever">Lever</option>
            </select>
          </label>
          <label>Identyfikator tablicy
            <input required minLength={2} maxLength={80} pattern="[a-zA-Z0-9_-]+" placeholder={provider === "greenhouse" ? "np. nazwa-firmy" : "np. firma"} value={slug} onChange={e => setSlug(e.target.value)}/>
            <small>Fragment adresu URL tablicy firmy — nie pełny adres.</small>
          </label>
          <label>Wyświetlana nazwa
            <input maxLength={100} placeholder="Nazwa pracodawcy (opcjonalnie)" value={label} onChange={e => setLabel(e.target.value)}/>
          </label>
          <button className="btn primary" type="submit" disabled={!!busy || managed >= 20}>{busy === "add" ? <LoaderCircle className="spin" size={15}/> : <Plus size={15}/>} Dodaj źródło</button>
          <p className="source-help"><CircleHelp size={14}/> Dodanie tablicy nie gwarantuje dostępności ofert. Jeśli identyfikator jest nieprawidłowy, zobaczysz błąd w historii skanowania.</p>
        </form>
      </section>
    </div>
    <div className="sources-info"><ShieldCheck size={18}/><p>JobPilot korzysta z publicznych interfejsów ogłoszeń. Nie pobiera treści LinkedIn przez boty i nie składa aplikacji bez Twojego działania. Klucze Adzuna nadal ustawiasz w zmiennych środowiskowych Dokploy.</p></div>
  </div>;
}

export function ManualJobDialog({ onClose, onImported, onError }: {
  onClose: () => void; onImported: (id: string) => void; onError: (s: string) => void;
}) {
  const [form, setForm] = useState<ManualForm>(emptyForm);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setSubmitError("");
    try {
      const result = await request<{ job_id: string }>("/api/jobs/manual", { method: "POST", body: JSON.stringify(form) });
      onImported(result.job_id);
    } catch (err) { setSubmitError((err as Error).message); onError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="manual-modal-scrim" onMouseDown={onClose}>
    <div role="dialog" aria-modal="true" aria-label="Ręcznie dodaj ogłoszenie" className="manual-modal" onMouseDown={e => e.stopPropagation()}>
      <div className="manual-modal-top"><div><div className="eyebrow">NOWE OGŁOSZENIE</div><h2>Dodaj ofertę ręcznie</h2>
        <p>Oferty spoza połączonych serwisów też możesz analizować i zapisywać.</p></div><button type="button" className="icon-button" onClick={onClose} aria-label="Zamknij"><X size={19}/></button></div>
      <form className="manual-modal-form" onSubmit={submit}>
        <label>Stanowisko<input autoFocus required minLength={3} maxLength={180} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Python Developer"/></label>
        <div className="manual-modal-columns">
          <label>Firma<input required minLength={2} maxLength={120} value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} placeholder="Nazwa firmy"/></label>
          <label>Lokalizacja<input maxLength={120} value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} placeholder="Poznań / Zdalnie"/></label>
        </div>
        <label>Link do oryginalnego ogłoszenia<input required type="url" pattern="https://.*" maxLength={2000} value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} placeholder="https://firma.pl/kariera/oferta"/></label>
        <label>Opis oferty<textarea required minLength={30} maxLength={12000} rows={6} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Wklej treść oferty, wymagania i zakres obowiązków..."/></label>
        <label className="source-inline-checkbox"><input type="checkbox" checked={form.remote} onChange={e => setForm({ ...form, remote: e.target.checked })}/> Oferta umożliwia pracę zdalną</label>
        {submitError && <p className="form-error" role="alert">{submitError}</p>}
        <div className="manual-modal-footer"><span><ShieldCheck size={14}/> Nie wysyłamy zgłoszenia do pracodawcy</span>
          <div><button className="btn secondary" type="button" onClick={onClose}>Anuluj</button><button className="btn primary" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={15}/> : <Check size={15}/>} Dodaj i oceń dopasowanie</button></div></div>
      </form>
    </div>
  </div>;
}
