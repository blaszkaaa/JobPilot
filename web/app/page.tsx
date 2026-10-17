"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, Bell, Bookmark, BrainCircuit,
  BriefcaseBusiness, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp,
  Clock3, ExternalLink, FileText, Filter, Globe2, LayoutDashboard, LoaderCircle,
  LockKeyhole, LogOut, MapPin, Menu, Radar, RefreshCcw, Search, Send,
  Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Target, X
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { SearchWatches, ApplicationBoard, CvUploader } from "./workspaces";

type Page = "dashboard" | "jobs" | "watches" | "applications" | "notifications" | "settings";
type Job = {
  id: string; title: string; company: string; location: string; remote: boolean;
  description: string; url: string; source: string; posted_at: string;
  score: number; reason: string; discovered_at: string; status: string;
};
type Profile = {
  full_name: string; location: string; keywords: string; excluded: string;
  cv_text: string; remote_only: boolean; min_score: number;
};
type Stats = {
  total: number; matched: number; saved: number; applied: number;
  telegram: boolean; sources: string[];
  last_sync: { at: string | null; error: string | null; count: number };
};
type Notice = { id: number; message: string; created_at: string };
type Application = { id: number; title: string; company: string; url: string; created_at: string; status: string };
const blankProfile: Profile = { full_name: "", location: "Polska", keywords: "", excluded: "", cv_text: "", remote_only: false, min_score: 60 };
const blankStats: Stats = { total: 0, matched: 0, saved: 0, applied: 0, telegram: false, sources: [], last_sync: { at: null, error: null, count: 0 } };
const menu: { page: Page; label: string; icon: LucideIcon }[] = [
  { page: "dashboard", label: "Przegląd", icon: LayoutDashboard },
  { page: "jobs", label: "Oferty pracy", icon: BriefcaseBusiness },
  { page: "watches", label: "Wyszukiwania", icon: Radar },
  { page: "applications", label: "Moje aplikacje", icon: Send },
  { page: "notifications", label: "Powiadomienia", icon: Bell },
  { page: "settings", label: "Ustawienia", icon: Settings2 }
];
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) }, ...options
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "Nie udało się wykonać operacji");
  }
  return response.json() as Promise<T>;
}
function shortDate(date: string | null) {
  if (!date) return "Jeszcze nie uruchomiono";
  const parsed = new Date(date);
  return Number.isNaN(parsed.valueOf()) ? "Brak danych" : parsed.toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" });
}
function formatSource(job: Job) { return job.source; }
function scoreClass(n: number) { return n >= 70 ? "high" : n >= 40 ? "medium" : "low"; }
function getInitials(text: string) { return text.split(/[\s-]+/).map(x => x[0]).filter(Boolean).slice(0, 2).join("").toUpperCase() || "JP"; }

function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await api("/api/login", { method: "POST", body: JSON.stringify({ email, password }) });
      onSuccess();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <div className="login-root">
    <div className="login-glow" />
    <form className="login-card" onSubmit={submit}>
      <div className="brand-icon large"><Radar size={25} strokeWidth={2.4} /></div>
      <h1>Witaj w JobPilot</h1>
      <p>Twoje centrum wyszukiwania i dopasowania ofert pracy.</p>
      <label>Adres e-mail<input autoComplete="username" required type="email" placeholder="email@przyklad.pl" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Hasło<input autoComplete="current-password" required type="password" placeholder="Wprowadź hasło" value={password} onChange={e => setPassword(e.target.value)} /></label>
      {error && <div className="form-error">{error}</div>}
      <button className="btn primary fill" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <LockKeyhole size={16}/>} Zaloguj się</button>
      <div className="login-foot"><ShieldCheck size={14}/> Prywatna instancja JobPilot</div>
    </form>
  </div>;
}

export default function Home() {
  const [auth, setAuth] = useState<"checking" | "guest" | "logged">("checking");
  const [email, setEmail] = useState("");
  const [page, setPage] = useState<Page>("dashboard");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [profile, setProfile] = useState<Profile>(blankProfile);
  const [stats, setStats] = useState<Stats>(blankStats);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chosen = jobs.find(j => j.id === selectedId) || null;
  const filtered = useMemo(() => jobs.filter(j => {
    const search = query.toLowerCase();
    return (status === "all" || j.status === status)
      && (!remoteOnly || j.remote)
      && (!search || [j.title, j.company, j.description, j.location].some(s => s.toLowerCase().includes(search)));
  }), [jobs, status, query, remoteOnly]);
  const recommended = jobs.filter(j => j.score >= profile.min_score && j.status !== "ignored").slice(0, 6);

  async function load() {
    try {
      const [loadedJobs, loadedProfile, loadedStats, loadedNotices, loadedApplications] = await Promise.all([
        api<Job[]>("/api/jobs"), api<Profile>("/api/profile"), api<Stats>("/api/stats"),
        api<Notice[]>("/api/notifications"), api<Application[]>("/api/applications")
      ]);
      setJobs(loadedJobs); setProfile(loadedProfile); setStats(loadedStats);
      setNotices(loadedNotices); setApplications(loadedApplications);
    } catch (err) { setError((err as Error).message); }
  }
  async function checkAuth() {
    try {
      const result = await api<{ email: string }>("/api/me");
      setEmail(result.email); setAuth("logged");
    } catch { setAuth("guest"); }
  }
  useEffect(() => { void checkAuth(); }, []);
  useEffect(() => { if (auth === "logged") void load(); }, [auth]);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(""), 4500); return () => clearTimeout(timer); } }, [toast]);

  async function synchronize() {
    setBusy("sync"); setError("");
    try {
      const result = await api<{ new_matches?: number }>("/api/jobs/refresh", { method: "POST" });
      await load(); setToast("Synchronizacja zakończona. Nowe dopasowania: " + (result.new_matches ?? 0));
    } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }
  async function changeStatus(job: Job, next: string) {
    setBusy(job.id);
    try {
      await api("/api/jobs/" + encodeURIComponent(job.id) + "/status", { method: "PATCH", body: JSON.stringify({ status: next }) });
      await load(); setToast(next === "saved" ? "Oferta zapisana" : next === "applied" ? "Aplikacja dodana do historii" : "Status zaktualizowany");
    } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }
  async function prepareApplication(job: Job) {
    setBusy("prepare");
    try {
      const result = await api<{ created: boolean }>("/api/applications/prepare", {
        method: "POST", body: JSON.stringify({ job_id: job.id })
      });
      await load();
      navigate("applications");
      setToast(result.created ? "Utworzono szkic aplikacji — sprawdź go przed wysłaniem" : "Otwórz istniejącą aplikację w pipeline");
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(""); }
  }

  async function saveProfile() {
    setBusy("profile");
    try {
      await api("/api/profile", { method: "PUT", body: JSON.stringify(profile) });
      await load(); setToast("Preferencje zapisane. Dopasowanie przeliczone.");
    } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }
  async function draft(job: Job) {
    setBusy("draft");
    try {
      const result = await api<{ draft: string }>("/api/jobs/" + encodeURIComponent(job.id) + "/draft", { method: "POST" });
      await navigator.clipboard.writeText(result.draft);
      setToast("Szkic wiadomości skopiowany do schowka (nie został wysłany)");
    } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }
  async function logout() {
    await api("/api/logout", { method: "POST" }).catch(() => undefined);
    setAuth("guest"); setJobs([]); setSelectedId(null);
  }
  function navigate(next: Page) { setPage(next); setSelectedId(null); setSidebarOpen(false); setError(""); }

  if (auth === "checking") return <div className="initial-loader"><Radar size={30}/><LoaderCircle className="spin" size={22}/></div>;
  if (auth === "guest") return <LoginScreen onSuccess={() => void checkAuth()}/>;

  return <div className="shell">
    <aside className={"sidebar " + (sidebarOpen ? "mobile-open" : "")}>
      <div className="brand"><div className="brand-icon"><Radar size={20} strokeWidth={2.4}/></div><span>JobPilot</span><span className="brand-version">beta</span></div>
      <div className="workspace"><div className="workspace-avatar">J</div><div className="workspace-text"><strong>My Workspace</strong><small>Personal instance</small></div><ChevronDown size={15}/></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav>{menu.map(item => <button key={item.page} className={"nav-item " + (page === item.page ? "active" : "")} onClick={() => navigate(item.page)}>
        <item.icon size={17}/><span>{item.label}</span>{item.page === "notifications" && notices.length > 0 && <span className="nav-count">{notices.length}</span>}
      </button>)}</nav>
      <div className="sidebar-bottom">
        <div className="sync-card"><div className="sync-title"><span className="pulse-dot"/> System aktywny</div><p>Automatyczne wyszukiwanie co 30 minut.</p><div className="sync-time"><Clock3 size={13}/> {shortDate(stats.last_sync.at)}</div></div>
        <button className="sidebar-account" onClick={logout}><div className="user-avatar">{getInitials(email)}</div><div><strong>{profile.full_name || "Administrator"}</strong><small>{email}</small></div><LogOut size={16}/></button>
      </div>
    </aside>
    {sidebarOpen && <button className="mobile-backdrop" aria-label="Zamknij menu" onClick={() => setSidebarOpen(false)}/>}
    <div className="main-area">
      <header className="topbar">
        <div className="top-left"><button className="icon-button mobile-toggle" onClick={() => setSidebarOpen(true)} aria-label="Otwórz menu"><Menu size={20}/></button>
          <span className="breadcrumb">Workspace</span><ChevronRight size={14} className="muted"/><span className="breadcrumb-current">{menu.find(m => m.page === page)?.label}</span>
        </div>
        <div className="top-actions"><span className="top-status"><span className="pulse-dot"/> Monitoring aktywny</span><button className="icon-button" onClick={() => navigate("notifications")} aria-label="Powiadomienia"><Bell size={18}/></button><div className="top-avatar">{getInitials(email)}</div></div>
      </header>
      <main className="content">
        {error && <div className="notice-error"><CircleHelp size={17}/>{error}<button onClick={() => setError("")} aria-label="Zamknij błąd"><X size={15}/></button></div>}
        {toast && <div className="toast"><CheckCircle2 size={17}/>{toast}</div>}
        {page === "dashboard" && <>
          <div className="heading-row"><div><div className="eyebrow"><Sparkles size={14}/> TWOJE CENTRUM KARIERY</div><h1>Przegląd</h1><p>Kontroluj poszukiwania pracy w jednym miejscu.</p></div>
            <button className="btn primary" disabled={busy === "sync"} onClick={synchronize}>{busy === "sync" ? <LoaderCircle size={16} className="spin"/> : <RefreshCcw size={16}/>} Skanuj oferty</button></div>
          <div className="stats-grid">
            <StatCard label="Znalezione oferty" value={stats.total} icon={BriefcaseBusiness} sub="Wszystkie źródła"/>
            <StatCard label="Dopasowane" value={stats.matched} icon={Target} sub={"Wynik ≥ " + profile.min_score + "%"} accent/>
            <StatCard label="Zapisane" value={stats.saved} icon={Bookmark} sub="Do przejrzenia"/>
            <StatCard label="Aplikacje" value={stats.applied} icon={Send} sub="Wysłane i w rekrutacji"/>
          </div>
          <div className="dashboard-grid">
            <section className="panel recommendations">
              <div className="panel-header"><div><h2><Sparkles size={18}/> Najlepsze dopasowania</h2><p>Ranking semantyczny i preferencje (nie szansa zatrudnienia)</p></div><button className="text-button" onClick={() => navigate("jobs")}>Wszystkie oferty <ArrowRight size={15}/></button></div>
              {recommended.length ? <div className="list-jobs">{recommended.map(job => <JobRow key={job.id} job={job} onClick={() => { navigate("jobs"); setSelectedId(job.id); }}/>)}</div> :
              <Empty icon={Radar} title="Czekamy na pierwsze oferty" message="Uruchom skanowanie i uzupełnij preferencje, aby otrzymać dopasowania."/>}
            </section>
            <div className="side-panels">
              <section className="panel small-panel"><div className="panel-header"><div><h2><Activity size={18}/> Aktywność</h2><p>Stan zbierania ogłoszeń</p></div></div>
                <div className="info-line"><span>Ostatni skan</span><strong>{shortDate(stats.last_sync.at)}</strong></div>
                <div className="info-line"><span>Przejrzane oferty</span><strong>{stats.last_sync.count}</strong></div>
                <div className="info-line"><span>Źródła</span><strong>{stats.sources.join(", ") || "Brak"}</strong></div>
                {stats.last_sync.error && <div className="inline-warning">{stats.last_sync.error}</div>}
              </section>
              <section className="panel small-panel"><div className="panel-header"><div><h2><BrainCircuit size={18}/> Matching Engine</h2><p>TF-IDF + reguły preferencji</p></div><span className="tag purple">LOCAL ML</span></div>
                <div className="engine-line"><div className="engine-orb"><BrainCircuit size={20}/></div><div><strong>Silnik jest gotowy</strong><p>Ocena CV i preferencji względem treści ofert. ChatGPT OAuth wymaga osobnego klienta lokalnego.</p></div></div>
                <button className="btn secondary fill" onClick={() => navigate("settings")}>Edytuj profil <ArrowRight size={15}/></button>
              </section>
            </div>
          </div>
        </>}
        {page === "jobs" && <>
          <div className="heading-row"><div><div className="eyebrow"><Globe2 size={14}/> JOB DISCOVERY</div><h1>Oferty pracy</h1><p>Przeglądaj, oceniaj i zapisuj dopasowane ogłoszenia.</p></div>
            <button className="btn primary" disabled={busy === "sync"} onClick={synchronize}>{busy === "sync" ? <LoaderCircle className="spin" size={16}/> : <RefreshCcw size={16}/>} Odśwież</button></div>
          <div className="filters"><div className="searchbox"><Search size={17}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Stanowisko, firma, umiejętności..." /></div>
            <div className="select-wrap"><Filter size={15}/><select aria-label="Status oferty" value={status} onChange={e => setStatus(e.target.value)}><option value="all">Wszystkie statusy</option><option value="new">Nowe</option><option value="saved">Zapisane</option><option value="applied">Aplikowano</option><option value="ignored">Odrzucone</option></select><ChevronDown size={13}/></div>
            <label className="toggle-filter"><input type="checkbox" checked={remoteOnly} onChange={e => setRemoteOnly(e.target.checked)}/> Tylko zdalne</label>
          </div>
          <div className="jobs-layout"><section className="panel job-list-panel">
            <div className="panel-bar"><strong>{filtered.length} ofert</strong><span>Sortowanie: najlepsze dopasowanie <ArrowDownRight size={14}/></span></div>
            {filtered.length ? <div className="list-jobs">{filtered.map(job => <JobRow key={job.id} job={job} selected={selectedId === job.id} onClick={() => setSelectedId(job.id)}/>)}</div> :
             <Empty icon={Search} title="Brak ofert" message="Zmień filtry albo rozpocznij skanowanie."/>}
          </section>
          <section className="panel detail-panel">{chosen ? <>
            <div className="detail-top"><div className="company-logo big">{getInitials(chosen.company)}</div><button className="icon-button" title="Zamknij szczegóły" onClick={() => setSelectedId(null)}><X size={18}/></button></div>
            <h2>{chosen.title}</h2><div className="company-name">{chosen.company}</div>
            <div className="chips"><span><MapPin size={13}/>{chosen.location}</span>{chosen.remote && <span>Remote</span>}<span>{formatSource(chosen)}</span></div>
            <div className="detail-score"><div><small>Wskaźnik dopasowania (szacunkowy)</small><strong>{chosen.score}%</strong></div><div className="bar"><span style={{ width: chosen.score + "%" }}/></div><p>{chosen.reason}</p></div>
            <h3>Opis stanowiska</h3><p className="job-description">{chosen.description || "Opis niedostępny — przejdź do ogłoszenia źródłowego."}</p>
            <div className="detail-actions"><a className="btn primary fill" href={chosen.url} target="_blank" rel="noopener noreferrer">Otwórz ofertę <ExternalLink size={15}/></a>
              <button disabled={busy === chosen.id} className="btn secondary fill" onClick={() => changeStatus(chosen, chosen.status === "saved" ? "new" : "saved")}><Bookmark size={15}/>{chosen.status === "saved" ? "Usuń z zapisanych" : "Zapisz ofertę"}</button>
              <button disabled={busy === "draft"} className="btn secondary fill" onClick={() => draft(chosen)}><FileText size={15}/> Kopiuj szkic wiadomości</button>
              <button disabled={busy === "prepare"} className="btn secondary fill" onClick={() => void prepareApplication(chosen)}><FileText size={15}/> Przygotuj aplikację</button>
              {chosen.status !== "ignored" && <button disabled={busy === chosen.id} className="btn ghost fill" onClick={() => changeStatus(chosen, "ignored")}><X size={15}/> Odrzuć ofertę</button>}
            </div>
          </> : <div className="detail-placeholder"><div className="placeholder-icon"><BriefcaseBusiness size={28}/></div><h3>Wybierz ofertę</h3><p>Kliknij ogłoszenie z listy, aby zobaczyć szczegóły, dopasowanie i dostępne działania.</p></div>}</section></div>
        </>}
        {page === "watches" && <SearchWatches sources={stats.sources} onMessage={setToast} onError={setError}/>}
        {page === "applications" && <ApplicationBoard onMessage={setToast} onError={setError} onChanged={load}/>}

        {page === "notifications" && <><PageHeading eyebrow="ALERT CENTER" icon={Bell} title="Powiadomienia" desc="Informacje o nowo znalezionych dopasowaniach."/>
          <section className="panel data-panel"><div className="panel-bar"><strong>Ostatnie zdarzenia</strong><span>Telegram: {stats.telegram ? "skonfigurowany" : "niepołączony"}</span></div>
            {notices.length ? notices.map(n => <div key={n.id} className="event-row"><div className="event-icon"><Bell size={17}/></div><div><strong>{n.message}</strong><small>{shortDate(n.created_at)}</small></div></div>) : <Empty icon={Bell} title="Brak powiadomień" message="Nowe oferty spełniające Twój próg dopasowania pojawią się tutaj."/>}</section>
        </>}
        {page === "settings" && <><PageHeading eyebrow="WORKSPACE CONFIGURATION" icon={SlidersHorizontal} title="Ustawienia" desc="Dopasuj profil zawodowy i zasady działania wyszukiwarki."/>
          <div className="settings-grid"><section className="panel settings-panel"><div className="panel-header"><div><h2><Target size={18}/> Preferencje zawodowe</h2><p>Używane do obliczania rankingu dopasowania</p></div></div>
            <div className="settings-form"><label>Imię i nazwisko<input maxLength={120} value={profile.full_name} onChange={e => setProfile({ ...profile, full_name: e.target.value })} placeholder="Twoje imię i nazwisko"/></label>
              <label>Lokalizacja<input maxLength={120} value={profile.location} onChange={e => setProfile({ ...profile, location: e.target.value })} placeholder="Np. Poznań, Polska"/></label>
              <label>Umiejętności i słowa kluczowe<small>Oddziel przecinkami</small><textarea rows={3} value={profile.keywords} onChange={e => setProfile({ ...profile, keywords: e.target.value })} placeholder="Python, REST API, FastAPI, AI"/></label>
              <label>Wykluczone frazy<small>Oferty zawierające te frazy otrzymają wynik 0%</small><input value={profile.excluded} onChange={e => setProfile({ ...profile, excluded: e.target.value })} placeholder="Np. Senior, staż"/></label>
              <label>Treść CV<small>Wklej tekst CV lub wczytaj plik PDF — nic nie jest wysyłane do zewnętrznego modelu</small><textarea rows={7} value={profile.cv_text} onChange={e => setProfile({ ...profile, cv_text: e.target.value })} placeholder="Opis doświadczenia, projektów i technologii..."/></label>
              <CvUploader onImported={text => setProfile(current => ({ ...current, cv_text: text }))} onMessage={setToast} onError={setError}/>
              <label className="checkbox-row"><input type="checkbox" checked={profile.remote_only} onChange={e => setProfile({ ...profile, remote_only: e.target.checked })}/><span>Uwzględniaj w rankingu tylko oferty zdalne</span></label>
              <label>Próg powiadomień: <strong>{profile.min_score}%</strong><input type="range" min="0" max="100" value={profile.min_score} onChange={e => setProfile({ ...profile, min_score: Number(e.target.value) })}/></label>
              <button className="btn primary" disabled={busy === "profile"} onClick={saveProfile}>{busy === "profile" ? <LoaderCircle className="spin" size={16}/> : <Check size={16}/>} Zapisz zmiany</button>
            </div>
          </section>
          <div className="settings-side"><section className="panel small-panel"><div className="panel-header"><div><h2><Globe2 size={18}/> Źródła ofert</h2><p>Aktywne integracje API</p></div></div>
            {["Arbeitnow", "Greenhouse", "Lever", "Adzuna"].map(source => <div className="info-line" key={source}><span>{source}</span><span className={"tag " + (stats.sources.includes(source) ? "green" : "")}>{stats.sources.includes(source) ? "Aktywne" : "Wymaga konfiguracji"}</span></div>)}
            <p className="subtle-note">Dodaj identyfikatory firm Greenhouse i Lever lub klucze Adzuna w zmiennych środowiskowych Dokploy.</p>
          </section><section className="panel small-panel"><div className="panel-header"><div><h2><ShieldCheck size={18}/> Integracja ChatGPT</h2><p>Bezpieczeństwo planu użytkownika</p></div></div>
            <div className="info-pill"><LockKeyhole size={15}/> OAuth nieaktywny na serwerze</div>
            <p className="subtle-note">Logowanie kontem ChatGPT i korzystanie z subskrypcji wymaga zgodnego z zasadami, lokalnego klienta Sign in with ChatGPT. Wersja serwerowa nie przechowuje tokenów ChatGPT.</p>
          </section></div></div>
        </>}
        <footer><span>JobPilot <span className="footer-dot">•</span> Open-source job discovery</span><span>Built for smarter job searches</span></footer>
      </main>
    </div>
  </div>;
}

function StatCard({ label, value, sub, icon: Icon, accent = false }: { label: string; value: number; sub: string; icon: LucideIcon; accent?: boolean }) {
  return <div className="stat-card"><div className="stat-heading"><span>{label}</span><span className={"stat-icon " + (accent ? "highlight" : "")}><Icon size={18}/></span></div><strong>{value.toLocaleString("pl-PL")}</strong><small>{sub}</small></div>;
}
function JobRow({ job, onClick, selected = false }: { job: Job; onClick: () => void; selected?: boolean }) {
  return <button className={"job-row " + (selected ? "selected" : "")} onClick={onClick}>
    <div className="company-logo">{getInitials(job.company)}</div><div className="job-main"><strong>{job.title}</strong><div className="job-meta"><span>{job.company}</span><span className="meta-dot">·</span><span>{job.location}</span>{job.remote && <span className="remote-label">Remote</span>}</div></div>
    <div className="job-row-right"><div className={"score " + scoreClass(job.score)}>{job.score}%</div><span>{job.source}{job.status === "saved" ? " · Zapisano" : job.status === "applied" ? " · Aplikowano" : ""}</span></div><ChevronRight className="job-chevron" size={17}/>
  </button>;
}
function Empty({ icon: Icon, title, message }: { icon: LucideIcon; title: string; message: string }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={24}/></div><h3>{title}</h3><p>{message}</p></div>;
}
function PageHeading({ eyebrow, icon: Icon, title, desc }: { eyebrow: string; icon: LucideIcon; title: string; desc: string }) {
  return <div className="heading-row"><div><div className="eyebrow"><Icon size={14}/>{eyebrow}</div><h1>{title}</h1><p>{desc}</p></div></div>;
}
