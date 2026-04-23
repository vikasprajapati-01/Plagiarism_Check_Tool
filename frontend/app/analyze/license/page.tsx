"use client";

import { useState, useRef } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, RadioGroup, SliderField, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type InputMode = "text" | "file";

export default function LicenseCheckPage() {
  const [inputMode, setInputMode] = useState<InputMode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [threshold, setThreshold] = useState(0.3);
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("xlsx");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setResult(null); setError(null);
    try {
      const fd = new FormData();
      if (inputMode === "text") {
        if (!text.trim()) throw new Error("Please enter text");
        fd.append("text", text.trim());
      } else {
        if (!file) throw new Error("Please select a file");
        fd.append("file", file);
      }
      fd.append("threshold", String(threshold));
      fd.append("download_report", String(downloadReport));
      fd.append("download_format", downloadFormat);

      const res = await fetch(`${API_BASE}/api/v1/license-check/check`, { method: "POST", body: fd });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `license_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="License / Copyright Check" subtitle="Open-source license fingerprinting — MIT · GPL · Apache · SPDX" icon="⚖️" color="#EF4444">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Input Method</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "text", label: "Paste text / code" },
                { value: "file", label: "Upload file (CSV / Excel / TXT)" },
              ]}
              value={inputMode}
              onChange={(v) => setInputMode(v as InputMode)}
            />

            {inputMode === "text" ? (
              <TextAreaField label="Text or Code to Check" value={text} onChange={setText} placeholder={"Paste license text or code snippet here...\ne.g. MIT License\nCopyright (c) 2024..."} required />
            ) : (
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                  Upload File <span style={{ color: "#EF4444" }}>*</span>
                </label>
                <div
                  onClick={() => fileRef.current?.click()}
                  style={{ border: "2px dashed var(--border)", borderRadius: 10, padding: "28px 20px", cursor: "pointer", textAlign: "center" }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "#EF4444")}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--border)")}
                >
                  <p style={{ fontSize: 14, color: "var(--text-secondary)" }}>{file ? `📄 ${file.name}` : "Click to select CSV, XLSX, or TXT"}</p>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>First column will be used as text source</p>
                </div>
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" style={{ display: "none" }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </div>
            )}
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Parameters</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <SliderField label="Confidence Threshold" value={threshold} onChange={setThreshold} min={0.1} max={1.0} step={0.05} />
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -8 }}>
              Lower values detect more licenses but with less certainty. 0.3 is recommended.
            </p>
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 10 }}>Report Format</p>
            <RadioGroup options={[{ value: "xlsx", label: "Excel (XLSX)" }, { value: "csv", label: "CSV" }]} value={downloadFormat} onChange={setDownloadFormat} />
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", fontSize: 14, fontWeight: 500, color: "var(--text-secondary)", marginTop: 8 }}>
              <input type="checkbox" checked={downloadReport} onChange={(e) => setDownloadReport(e.target.checked)} style={{ width: 16, height: 16, accentColor: "#EF4444" }} />
              Download report after analysis
            </label>
          </div>
        </div>

        <SubmitButton loading={loading} color="#EF4444" />
      </form>

      <ResultPanel result={result} error={error} color="#EF4444" renderResult={(r) => (
        <>
          {r.has_license !== undefined && <ResultRow label="License Detected" value={r.has_license ? "⚠️ License found" : "🟢 No license found"} highlight={r.has_license} />}
          {r.risk_level && <ResultRow label="Risk Level" value={r.risk_level.toUpperCase()} highlight={r.risk_level !== "none"} />}
          {r.total_matches !== undefined && <ResultRow label="Total Matches" value={String(r.total_matches)} />}
          {r.primary_license && (
            <>
              <ResultRow label="Primary License" value={`${r.primary_license.name} (${r.primary_license.spdx_id})`} />
              <ResultRow label="Confidence" value={(r.primary_license.confidence * 100).toFixed(1) + "%"} />
              {r.primary_license.license_url && (
                <div style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                  <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>License URL</p>
                  <a href={r.primary_license.license_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: "var(--accent)", wordBreak: "break-all" }}>{r.primary_license.license_url}</a>
                </div>
              )}
            </>
          )}
          {r.total !== undefined && <ResultRow label="Total Texts Processed" value={String(r.total)} />}
          {r.licenses_found !== undefined && <ResultRow label="Texts with Licenses" value={String(r.licenses_found)} highlight={r.licenses_found > 0} />}
        </>
      )} />
    </AnalyzerLayout>
  );
}
