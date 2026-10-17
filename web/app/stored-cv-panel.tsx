"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Download, FileText, LoaderCircle, ShieldCheck, Trash2, UploadCloud } from "lucide-react";

type StoredCvInfo = {
  filename: string; sha256: string; pages: number; uploaded_at: string; size_bytes: number;
};
type StoredCvStatus = { exists: boolean; file: StoredCvInfo | null };

export function StoredCvPanel({ onSaved, onMessage, onError }: {
  onSaved: () => Promise<void>; onMessage: (text: string) => void; onError: (text: string) => void;
}) {
  const [status, setStatus] = useState<StoredCvStatus | null>(null);
  const [busy, setBusy] = useState("");
  const reload = useCallback(async () => {
    const response = await fetch("/api/profile/cv/file", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Nie można odczytać stanu CV");
    setStatus(await response.json() as StoredCvStatus);
  }, []);
  useEffect(() => { void reload().catch(error => onError((error as Error).message)); }, [reload, onError]);
  async function upload(file: File | null) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 2 * 1024 * 1024) {
      onError("Wybierz plik PDF nie większy niż 2 MB"); return;
    }
    setBusy("upload");
    try {
      const response = await fetch("/api/profile/cv/file", {
        method: "POST", credentials: "same-origin", body: file,
        headers: { "Content-Type": "application/pdf", "X-CV-Filename": file.name.replace(/[^\x20-\x7E]/g, "_") }
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Nie udało się zapisać CV");
      await Promise.all([reload(), onSaved()]);
      onMessage("CV zostało zapisane prywatnie na serwerze. Profil i dopasowania zaktualizowano.");
    } catch (error) { onError((error as Error).message); }
    finally { setBusy(""); }
  }
  async function download() {
    setBusy("download");
    try {
      const response = await fetch("/api/profile/cv/file/download", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Nie udało się pobrać CV");
      const file = await response.blob();
      const url = URL.createObjectURL(file);
      const element = document.createElement("a");
      element.href = url;
      element.download = status?.file?.filename || "CV.pdf";
      element.click();
      URL.revokeObjectURL(url);
    } catch (error) { onError((error as Error).message); }
    finally { setBusy(""); }
  }
  async function remove() {
    if (!window.confirm("Usunąć zapisany plik PDF? Tekst CV pozostanie w profilu do ręcznego usunięcia.")) return;
    setBusy("delete");
    try {
      const response = await fetch("/api/profile/cv/file", { method: "DELETE", credentials: "same-origin" });
      if (!response.ok) throw new Error("Nie udało się usunąć pliku");
      await reload();
      onMessage("Usunięto PDF. Tekst CV w profilu pozostaje bez zmian.");
    } catch (error) { onError((error as Error).message); }
    finally { setBusy(""); }
  }
  const file = status?.file;
  return <section className="private-cv-panel">
    <div className="private-cv-heading"><div><FileText size={18}/><strong>Twój dokument CV</strong></div>
      <span className={"tag " + (file ? "green" : "")}>{file ? "Zapisany na serwerze" : "Brak pliku"}</span>
    </div>
    {file && <div className="private-cv-file"><div className="private-cv-symbol"><FileText size={22}/></div>
      <div><strong>{file.filename}</strong><small>PDF · {(file.size_bytes / 1024).toFixed(0)} KB · {file.pages} str.</small>
        <small>Dodano: {new Date(file.uploaded_at).toLocaleString("pl-PL")}</small></div><CheckCircle2 size={17} color="#80d7a5"/>
    </div>}
    <div className="private-cv-buttons">
      <label className="btn primary private-cv-upload"><UploadCloud size={15}/>{busy === "upload" ? "Zapisywanie..." : file ? "Zastąp CV" : "Wgraj PDF CV"}
        <input type="file" accept=".pdf,application/pdf" disabled={!!busy} onChange={event => {
          const file = event.target.files?.[0] ?? null;
          event.target.value = "";
          void upload(file);
        }}/></label>
      {file && <><button className="btn secondary" disabled={!!busy} onClick={() => void download()}>
        {busy === "download" ? <LoaderCircle className="spin" size={15}/> : <Download size={15}/>} Pobierz</button>
        <button className="btn secondary" disabled={!!busy} onClick={() => void remove()}><Trash2 size={15}/> Usuń PDF</button></>}
    </div>
    <p className="private-cv-disclaimer"><ShieldCheck size={15}/>
      Plik PDF i jego tekst są przechowywane w prywatnej bazie danych tej instancji JobPilot.
      Wgranie dokumentu nadpisze tekst CV w profilu i przeliczy dopasowania. Samo wgranie CV nie wysyła żadnych aplikacji.
      Usunięcie pliku nie usuwa wyodrębnionego tekstu — można go skasować oddzielnie w polu „Treść CV”.
    </p>
  </section>;
}
