"use client";

import { useState } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, InputField, RadioGroup, SliderField, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Mode = "single" | "batch-within";
type Scope = "global" | "batch-name" | "batch-id";

export default function FuzzyDetectPage() {
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
  const [result, setResult] = useState<unknown | null>(null);
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
        res = await fetch(`${API_BASE}/api/v1/detect/fuzzy`, { method: "POST", body: fd });
      } else {
        const texts = batchTexts.split("\n").map((t) => t.trim()).filter(Boolean);
        res = await fetch(`${API_BASE}/api/v1/detect/batch-fuzzy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texts, threshold, download_report: downloadReport, download_format: downloadFormat }),
        });
      }
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `fuzzy_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="Fuzzy / Near-Duplicate Detection" subtitle="Levenshtein · Hamming · Jaccard · N-gram similarity" icon="〰️" color="#8B5CF6">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Detection Mode</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "single", label: "Single text vs. stored batch" },
                { value: "batch-within", label: "Check duplicates within a batch" },
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
                <TextAreaField label="Text to Check" value={text} onChange={setText} placeholder="Enter the text to compare..." required />
                <RadioGroup
                  options={[
                    { value: "global", label: "Global scope" },
                    { value: "batch-name", label: "By batch name" },
                    { value: "batch-id", label: "By batch UUID" },
                  ]}
                  value={scope}
                  onChange={(v) => setScope(v as Scope)}
                />
                {scope === "batch-name" && <InputField label="Batch Name" value={batchName} onChange={setBatchName} placeholder="e.g. Q1-2024-dataset" />}
                {scope === "batch-id" && <InputField label="Batch UUID" value={batchId} onChange={setBatchId} placeholder="e.g. 550e8400-..." />}
              </>
            ) : (
              <TextAreaField label="Texts (one per line)" value={batchTexts} onChange={setBatchTexts} placeholder={"Text entry 1\nText entry 2\nText entry 3"} required />
            )}
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Parameters</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <SliderField label="Similarity Threshold" value={threshold} onChange={setThreshold} min={0.5} max={1.0} step={0.01} />
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -8 }}>Minimum score to flag as duplicate. 0.85 recommended.</p>
          </div>
        </div>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />
        <SubmitButton loading={loading} color="#8B5CF6" />
      </form>

      <ResultPanel result={result} error={error} color="#8B5CF6" renderResult={(r) => {
        const isDuplicate = r.is_duplicate === true;
        const hasIsDuplicate = typeof r.is_duplicate === "boolean";
        const matchedText = typeof r.matched_text === "string" ? r.matched_text : null;
        const thresholdUsed = typeof r.threshold === "number" ? r.threshold : (typeof r.threshold === "string" ? r.threshold : null);
        const duplicatePairs = typeof r.duplicate_pairs === "number" ? r.duplicate_pairs : null;
        const totalTexts = typeof r.total_texts === "number" ? r.total_texts : null;

        return (
          <>
            {hasIsDuplicate && (
              <ResultRow
                label="Duplicate"
                value={isDuplicate ? "✅ Duplicate found" : "🟢 No duplicate"}
                highlight={isDuplicate}
              />
            )}
            {matchedText && <ResultRow label="Matched Text" value={matchedText} />}
            {thresholdUsed !== null && <ResultRow label="Threshold Used" value={String(thresholdUsed)} />}
            {duplicatePairs !== null && (
              <ResultRow
                label="Duplicate Pairs Found"
                value={String(duplicatePairs)}
                highlight={duplicatePairs > 0}
              />
            )}
            {totalTexts !== null && <ResultRow label="Total Texts Checked" value={String(totalTexts)} />}
          </>
        );
      }} />
    </AnalyzerLayout>
  );
}
