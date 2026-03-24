"use client";

import { useState } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, InputField, RadioGroup, SliderField, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Mode = "single" | "batch";

export default function WebScanPage() {
  const [mode, setMode] = useState<Mode>("single");
  const [text, setText] = useState("");
  const [batchTexts, setBatchTexts] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const [maxQueries, setMaxQueries] = useState(3);
  const [maxResultsPerQuery, setMaxResultsPerQuery] = useState(5);
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("excel");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setResult(null); setError(null);
    try {
      let res: Response;
      if (mode === "single") {
        const fd = new FormData();
        fd.append("text", text.trim());
        fd.append("threshold", String(threshold));
        fd.append("max_queries", String(maxQueries));
        fd.append("max_results_per_query", String(maxResultsPerQuery));
        fd.append("download_report", String(downloadReport));
        fd.append("download_format", downloadFormat);
        res = await fetch(`${API_BASE}/api/v1/web-scan/scan`, { method: "POST", body: fd });
      } else {
        const texts = batchTexts.split("\n").map((t) => t.trim()).filter(Boolean);
        res = await fetch(`${API_BASE}/api/v1/web-scan/batch-scan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texts, threshold, max_queries: maxQueries, max_results_per_query: maxResultsPerQuery, download_report: downloadReport, download_format: downloadFormat }),
        });
      }
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `web_scan_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="Web Plagiarism Scan" subtitle="DuckDuckGo search · Web fingerprinting · Live source matching" icon="🌐" color="#10B981">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Mode</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "single", label: "Single text" },
                { value: "batch", label: "Multiple texts" },
              ]}
              value={mode}
              onChange={(v) => setMode(v as Mode)}
            />
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Input</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            {mode === "single"
              ? <TextAreaField label="Text to Scan" value={text} onChange={setText} placeholder="Enter text to scan against the live web..." required />
              : <TextAreaField label="Texts (one per line)" value={batchTexts} onChange={setBatchTexts} placeholder={"Text entry 1\nText entry 2"} required />
            }
            <div style={{ marginTop: 4, padding: "10px 14px", background: "#10B98114", border: "1px solid #10B98130", borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: "#10B981", fontWeight: 500 }}>
                ⚠️ Keep <code>max_results_per_query</code> low (2–3) for batch mode to avoid rate limiting.
              </p>
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Search Parameters</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <SliderField label="Similarity Threshold" value={threshold} onChange={setThreshold} min={0.3} max={0.9} step={0.05} />
            <SliderField label="Max Search Queries" value={maxQueries} onChange={(v) => setMaxQueries(Math.round(v))} min={1} max={10} step={1} />
            <SliderField label="Max Results per Query" value={maxResultsPerQuery} onChange={(v) => setMaxResultsPerQuery(Math.round(v))} min={1} max={10} step={1} />
          </div>
        </div>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />
        <SubmitButton loading={loading} color="#10B981" />
      </form>

      <ResultPanel result={result} error={error} color="#10B981" renderResult={(r) => (
        <>
          {r.is_plagiarism !== undefined && <ResultRow label="Plagiarism Detected" value={r.is_plagiarism ? "⚠️ YES — Found on web" : "🟢 CLEAN"} highlight={r.is_plagiarism} />}
          {r.best_score !== undefined && <ResultRow label="Best Similarity Score" value={(r.best_score * 100).toFixed(1) + "%"} />}
          {r.best_url && (
            <div style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>Best Match URL</p>
              <a href={r.best_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: "var(--accent)", wordBreak: "break-all" }}>{r.best_url}</a>
            </div>
          )}
          {r.total_urls_checked !== undefined && <ResultRow label="URLs Checked" value={String(r.total_urls_checked)} />}
          {r.matches_found !== undefined && <ResultRow label="Matches Found" value={String(r.matches_found)} />}
          {r.plagiarism_detected !== undefined && <ResultRow label="Texts with Plagiarism" value={String(r.plagiarism_detected)} highlight={r.plagiarism_detected > 0} />}
        </>
      )} />
    </AnalyzerLayout>
  );
}
