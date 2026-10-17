"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, BriefcaseBusiness, Check, CheckCircle2, ChevronDown,
  ClipboardCopy, FileSearch, FileText, LoaderCircle, Search, ShieldCheck,
  Sparkles, Target, TriangleAlert, X
} from "lucide-react";

type JobOption = { id: string; title: string; company: string; score: number; location: string; source: string };
type Evidence = { skill: string; job_evidence: string; cv_evidence?: string };
type Report = {
  job_id: string; title: string; company: string; cv_present: boolean;
  matched: Evidence[]; unconfirmed: Evidence[]; mentioned: string[];
  detected_count: number; coverage_percent: number | null;
  note: string; method: string;
};
type Props = {
  jobs: JobOption[];
  initialJobId: string;
  onOpenJob: (jobId: string) => void;
  onEditCv: () => void;
  onMessage: (text: string) => void;
};

export function CVAnalysisWorkspace({ jobs, initialJobId, onOpenJob, onEditCv, onMessage }: Props) {
  const [selectedId, setSelectedId] = useState(initialJobId || jobs[0]?.id || "");
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const visibleJobs = useMemo(() => jobs.filter(job =>
    (job.title + " " + job.company).toLocaleLowerCase("pl").includes(search.trim().toLocaleLowerCase("pl"))
  ), [jobs, search]);

  useEffect(() => {
    if (!selectedId && jobs.length) setSelectedId(initialJobId || jobs[0].id);
  }, [jobs, selectedId, initialJobId]);

  useEffect(() => {
    if (!selectedId) { setReport(null); return; }
    const controller = new AbortController();
    setLoading(true); setError(""); setReport(null);
    fetch("/api/cv-analysis/" + encodeURIComponent(selectedId), {
      credentials: "same-origin", cache: "no-store", signal: controller.signal
    }).then(async response => {
      const json = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof json.detail === "string" ? json.detail : "Błąd analizy CV");
      return json as Report;
    }).then(setReport).catch(err => {
      if (!controller.signal.aborted) setError((err as Error).message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [selectedId]);

  async function copyReport() {
    if (!report || !report.cv_present) return;
    const matched = report.matched.map(item =>
      "- " + item.skill + "\n  CV: " + item.cv_evidence + "\n  Oferta: " + item.job_evidence).join("\n");
    const missing = report.unconfirmed.map(item =>
      "- " + item.skill + "\n  Oferta: " + item.job_evidence).join("\n");
    const output = [
      "JOBPILOT — ANALIZA CV I OGŁOSZENIA",
      report.title + " — " + report.company,
      "Wzmianki o technologiach: " + report.detected_count,
      "Potwierdzone w CV: " + report.matched.length,
      "Niewymienione w CV: " + report.unconfirmed.length,
      "Pokrycie wykrytych wzmianek: " + (report.coverage_percent ?? "brak danych") + "%",
      "",
      "POTWIERDZONE W CV",
      matched || "Brak potwierdzonych wzmianek.",
      "",
      "NIEWYMIENIONE W CV — DO WERYFIKACJI",
      missing || "Brak.",
      "",
      report.note,
      report.method,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(output);
      onMessage("Raport analizy CV skopiowany do schowka");
    } catch { setError("Przeglądarka zablokowała kopiowanie do schowka."); }
  }

  return <div className="cv-analysis-workspace">
    <div className="heading-row">
      <div><div className="eyebrow"><FileSearch size={14}/> PROFIL ZAWODOWY</div>
        <h1>Analiza CV</h1>
        <p>Sprawdź, które technologie z ogłoszenia są potwierdzone w tekście Twojego CV.</p>
      </div>
      <button className="btn secondary" onClick={onEditCv}><FileText size={15}/> Edytuj CV</button>
    </div>
    <div className="cv-analysis-overview">
      <div className="cv-overview-icon"><ShieldCheck size={19}/></div>
      <div><strong>Analiza lokalna — bez wysyłania dokumentu</strong>
        <p>Porównanie jest oparte na wykrywaniu nazw technologii, nie na modelu ChatGPT. Nie ocenia rzeczywistego poziomu umiejętności ani szansy zatrudnienia.</p>
      </div>
    </div>
    <div className="cv-analysis-layout">
      <section className="panel cv-selector">
        <div className="panel-header"><div><h2><BriefcaseBusiness size={17}/> Wybierz ogłoszenie</h2>
          <p>Oferty zapisane w JobPilot</p></div><span className="tag">{jobs.length}</span></div>
        <div className="cv-selector-search"><Search size={15}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Stanowisko lub firma..." aria-label="Znajdź ofertę"/></div>
        <div className="cv-selector-list">
          {visibleJobs.length ? visibleJobs.map(job =>
            <button key={job.id} className={"cv-select-job " + (selectedId === job.id ? "selected" : "")}
              onClick={() => setSelectedId(job.id)} aria-pressed={selectedId === job.id}>
              <div className="cv-job-symbol">{job.company.split(/\s+/).slice(0,2).map(word => word[0]).join("").toUpperCase()}</div>
              <div className="cv-job-label"><strong>{job.title}</strong><small>{job.company} · {job.source}</small></div>
              <span className="cv-job-fit">{job.score}%</span>
            </button>
          ) : <p className="cv-no-jobs">{jobs.length ? "Brak ofert pasujących do wyszukiwania." : "Najpierw pobierz lub dodaj ogłoszenia w zakładce Oferty pracy."}</p>}
        </div>
      </section>
      <section className="panel cv-analysis-report">
        {loading ? <div className="cv-analysis-state"><LoaderCircle className="spin" size={25}/><strong>Analizowanie ogłoszenia...</strong></div> :
          error ? <div className="cv-analysis-state"><TriangleAlert size={25}/><strong>Nie udało się przygotować analizy</strong><p>{error}</p>
            <button className="btn secondary" onClick={() => setSelectedId("")}>Wybierz inną ofertę</button></div> :
          !report ? <div className="cv-analysis-state"><FileSearch size={25}/><strong>Wybierz ofertę z listy</strong><p>Raport pojawi się tutaj.</p></div> :
          <>
            <div className="cv-report-title"><div><span className="cv-microtitle">PORÓWNANIE CV Z OFERTĄ</span><h2>{report.title}</h2><p>{report.company}</p></div>
              <button className="icon-button" title="Otwórz ogłoszenie" aria-label="Otwórz ogłoszenie" onClick={() => onOpenJob(report.job_id)}><ArrowRight size={18}/></button></div>
            {!report.cv_present ? <div className="cv-empty-profile"><FileText size={24}/><h3>Najpierw dodaj CV</h3>
              <p>{report.note}</p><button className="btn primary" onClick={onEditCv}>Uzupełnij CV <ArrowRight size={15}/></button></div> :
              <>
                <div className="cv-report-metrics">
                  <div><small>Potwierdzone wzmianki</small><strong>{report.matched.length}</strong></div>
                  <div><small>Do zweryfikowania</small><strong>{report.unconfirmed.length}</strong></div>
                  <div><small>Pokrycie wzmianek</small><strong>{report.coverage_percent === null ? "—" : report.coverage_percent + "%"}</strong></div>
                </div>
                {report.coverage_percent !== null && <div className="cv-meter" role="progressbar"
                  aria-label="Pokrycie wykrytych technologii w CV" aria-valuemin={0} aria-valuemax={100} aria-valuenow={report.coverage_percent}>
                  <span style={{width: report.coverage_percent + "%"}}/></div>}
                <p className="cv-score-disclaimer">{report.note}</p>
                <div className="cv-report-actions">
                  <button className="btn secondary" onClick={() => void copyReport()}><ClipboardCopy size={15}/> Kopiuj raport</button>
                  <button className="btn secondary" onClick={() => onOpenJob(report.job_id)}><ArrowRight size={15}/> Szczegóły oferty</button>
                </div>
                {report.detected_count === 0 ? <div className="cv-skill-empty"><Sparkles size={22}/><h3>Nie wykryto nazw technologii</h3><p>Ta oferta może dotyczyć kompetencji miękkich lub nie używać standardowych nazw narzędzi.</p></div> :
                  <div className="cv-report-sections">
                    <section className="cv-skill-section"><div className="cv-section-heading"><CheckCircle2 size={17}/><h3>Potwierdzone w CV</h3><span>{report.matched.length}</span></div>
                      {report.matched.length ? <div className="cv-skill-list">{report.matched.map(item => <article className="cv-skill-row" key={item.skill}>
                        <div className="cv-skill-head"><span className="cv-skill-tag matched"><Check size={13}/>{item.skill}</span></div>
                        <div className="cv-evidence-label">FRAGMENT CV</div>
                        <p>{item.cv_evidence}</p>
                        <div className="cv-evidence-label">FRAGMENT OFERTY</div>
                        <p>{item.job_evidence}</p>
                      </article>)}</div> : <p className="cv-skill-empty-text">Brak rozpoznanych technologii wspomnianych jednocześnie w ogłoszeniu i CV.</p>}
                    </section>
                    <section className="cv-skill-section"><div className="cv-section-heading uncertain"><Target size={17}/><h3>Niepotwierdzone w CV</h3><span>{report.unconfirmed.length}</span></div>
                      {report.unconfirmed.length ? <div className="cv-skill-list">{report.unconfirmed.map(item => <article className="cv-skill-row" key={item.skill}>
                        <div className="cv-skill-head"><span className="cv-skill-tag unconfirmed">{item.skill}</span></div>
                        <div className="cv-evidence-label">WSPOMNIANE W OFERCIE</div><p>{item.job_evidence}</p>
                        <span className="cv-skill-hint">Jeżeli posiadasz tę umiejętność, warto opisać konkretne doświadczenie w CV.</span>
                      </article>)}</div> : <p className="cv-skill-empty-text">Wszystkie rozpoznane technologie z ogłoszenia zostały wymienione w CV.</p>}
                    </section>
                  </div>}
              </>}
            <div className="cv-report-footer"><ShieldCheck size={14}/><span>{report.method}</span></div>
          </>}
      </section>
    </div>
  </div>;
}
