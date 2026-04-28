"use client";

import { useState, useRef } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, RadioGroup, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type InputMode = "text" | "file";

export default function AIDetectPage() {
  const [inputMode, setInputMode] = useState<InputMode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("excel");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown | null>(null);
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
      fd.append("download_report", String(downloadReport));
      fd.append("download_format", downloadFormat);

      const res = await fetch(`${API_BASE}/api/v1/ai-detect/check`, { method: "POST", body: fd });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `ai_detection_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="AI Content Detection" subtitle="RoBERTa-based classifier for AI-generated text identification" icon="🤖" color="#F59E0B">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Input Method</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "text", label: "Paste text directly" },
                { value: "file", label: "Upload file (CSV / Excel / TXT)" },
              ]}
              value={inputMode}
              onChange={(v) => setInputMode(v as InputMode)}
            />

            {inputMode === "text" ? (
              <TextAreaField label="Text to Analyze" value={text} onChange={setText} placeholder="Paste content here to check if it was AI-generated..." required />
            ) : (
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                  Upload File <span style={{ color: "#EF4444" }}>*</span>
                </label>
                <div
                  onClick={() => fileRef.current?.click()}
                  style={{
                    border: "2px dashed var(--border)", borderRadius: 10, padding: "28px 20px",
                    cursor: "pointer", textAlign: "center", transition: "border-color 0.2s",
                  }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "#F59E0B")}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--border)")}
                >
                  <p style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                    {file ? `📄 ${file.name}` : "Click to select CSV, XLSX, or TXT file"}
                  </p>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>First column will be used as text source</p>
                </div>
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" style={{ display: "none" }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </div>
            )}

            <div style={{ marginTop: 16, padding: "10px 14px", background: "#F59E0B14", border: "1px solid #F59E0B30", borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: "#D97706", fontWeight: 500 }}>
                ℹ️ Requires <code>transformers</code> + <code>torch</code> on backend. Model: roberta-base-openai-detector
              </p>
            </div>
          </div>
        </div>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />
        <SubmitButton loading={loading} color="#F59E0B" />
      </form>

      <ResultPanel result={result} error={error} color="#F59E0B" renderResult={(r) => {
        const label = typeof r.label === "string" ? r.label : null;
        const confidence = typeof r.confidence === "number" ? r.confidence : null;
        const rawLabel = typeof r.raw_label === "string" ? r.raw_label : null;
        const total = typeof r.total === "number" ? r.total : null;
        const results = Array.isArray(r.results) ? r.results : null;

        return (
          <>
            {label && (
              <ResultRow
                label="Classification"
                value={label === "AI" ? "🤖 AI-Generated" : "✍️ Human-Written"}
                highlight={label === "AI"}
              />
            )}
            {confidence !== null && <ResultRow label="Confidence" value={(confidence * 100).toFixed(1) + "%"} />}
            {rawLabel && <ResultRow label="Raw Model Label" value={rawLabel} />}
            {total !== null && <ResultRow label="Total Texts Processed" value={String(total)} />}

            {results && (
              <div style={{ marginTop: 12 }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>Per-text results:</p>
                {results.slice(0, 10).map((item: unknown, i: number) => {
                  const obj = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
                  const itemPreview = typeof obj.text_preview === "string" ? obj.text_preview : "";
                  const itemLabel = typeof obj.label === "string" ? obj.label : "";
                  const itemConf = typeof obj.confidence === "number" ? obj.confidence : null;
                  const isAI = itemLabel === "AI";
                  const pct = itemConf !== null ? (itemConf * 100).toFixed(0) : "?";
                  return (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)", fontSize: 13 }}>
                      <span style={{ color: "var(--text-secondary)", flex: 1, marginRight: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {itemPreview}
                      </span>
                      <span style={{ fontWeight: 700, color: isAI ? "#EF4444" : "#22C55E", flexShrink: 0 }}>
                        {itemLabel || "—"} ({pct}%)
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        );
      }} />
    </AnalyzerLayout>
  );
}
