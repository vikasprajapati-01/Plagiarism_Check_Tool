"use client";

import { useState } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, InputField, RadioGroup, SliderField, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Mode = "single" | "batch-within";
type Scope = "global" | "batch-name" | "batch-id";

export default function SemanticDetectPage() {
  const [mode, setMode] = useState<Mode>("single");
  const [text, setText] = useState("");
  const [batchTexts, setBatchTexts] = useState("");
  const [scope, setScope] = useState<Scope>("global");
  const [batchId, setBatchId] = useState("");
  const [batchName, setBatchName] = useState("");
  const [threshold, setThreshold] = useState(0.85);
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
        if (scope === "batch-id" && batchId) fd.append("batch_id", batchId.trim());
        if (scope === "batch-name" && batchName) fd.append("batch_name", batchName.trim());
        fd.append("download_report", String(downloadReport));
        fd.append("download_format", downloadFormat);
        res = await fetch(`${API_BASE}/api/v1/detect/semantic`, { method: "POST", body: fd });
      } else {
        const texts = batchTexts.split("\n").map((t) => t.trim()).filter(Boolean);
        res = await fetch(`${API_BASE}/api/v1/detect/batch-semantic`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texts, threshold, download_report: downloadReport, download_format: downloadFormat }),
        });
      }
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `semantic_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="Semantic Similarity Detection" subtitle="SBERT · BERT · Cosine similarity for meaning-aware comparison" icon="🧠" color="#06B6D4">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Detection Mode</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "single", label: "Single text vs. stored batch" },
                { value: "batch-within", label: "Find duplicates within a new batch" },
              ]}
              value={mode}
              onChange={(v) => setMode(v as Mode)}
            />
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Input</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            {mode === "single" ? (
              <>
                <TextAreaField label="Text to Check" value={text} onChange={setText} placeholder="Enter text to check for semantic similarity..." required />
                <RadioGroup
                  options={[
                    { value: "global", label: "Global scope" },
                    { value: "batch-name", label: "By batch name" },
                    { value: "batch-id", label: "By batch UUID" },
                  ]}
                  value={scope}
                  onChange={(v) => setScope(v as Scope)}
                />
                {scope === "batch-name" && <InputField label="Batch Name" value={batchName} onChange={setBatchName} placeholder="e.g. training-data-v2" />}
                {scope === "batch-id" && <InputField label="Batch UUID" value={batchId} onChange={setBatchId} placeholder="e.g. 550e8400-..." />}
              </>
            ) : (
              <>
                <TextAreaField label="Texts (one per line, minimum 2)" value={batchTexts} onChange={setBatchTexts} placeholder={"The quick brown fox\nA fast auburn canine\nCompletely unrelated text"} required />
              </>
            )}
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Parameters</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <SliderField label="Cosine Similarity Threshold" value={threshold} onChange={setThreshold} min={0.5} max={1.0} step={0.01} />
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -8 }}>
              Higher = stricter. Recommend 0.85 for near-duplicates, 0.70 for paraphrase detection.
            </p>
            <div style={{ marginTop: 14, padding: "10px 14px", background: "#06B6D414", border: "1px solid #06B6D430", borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: "#06B6D4", fontWeight: 500 }}>
                ℹ️ Requires <code>sentence-transformers</code> installed on the backend. Model: all-MiniLM-L6-v2
              </p>
            </div>
          </div>
        </div>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />
        <SubmitButton loading={loading} color="#06B6D4" />
      </form>

      <ResultPanel result={result} error={error} color="#06B6D4" renderResult={(r) => (
        <>
          {r.is_duplicate !== undefined && <ResultRow label="Semantic Duplicate" value={r.is_duplicate ? "✅ Match found" : "🟢 No duplicate"} highlight={r.is_duplicate} />}
          {r.similarity_score !== undefined && <ResultRow label="Cosine Similarity" value={(r.similarity_score * 100).toFixed(1) + "%"} />}
          {r.matched_text && <ResultRow label="Closest Match" value={r.matched_text} />}
          {r.threshold && <ResultRow label="Threshold" value={String(r.threshold)} />}
          {r.duplicate_pairs !== undefined && <ResultRow label="Duplicate Pairs" value={String(r.duplicate_pairs)} highlight={r.duplicate_pairs > 0} />}
          {r.total_texts !== undefined && <ResultRow label="Total Texts" value={String(r.total_texts)} />}
        </>
      )} />
    </AnalyzerLayout>
  );
}
