"use client";

import { useState } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import {
  TextAreaField, RadioGroup, SliderField, ReportSection, SubmitButton, ResultPanel, ResultRow,
} from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Method = "exact" | "fuzzy" | "semantic";

export default function CrossBatchPage() {
  const [texts, setTexts] = useState("");
  const [method, setMethod] = useState<Method>("fuzzy");
  const [threshold, setThreshold] = useState(0.85);
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("excel");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setResult(null); setError(null);
    const textList = texts.split("\n").map((t) => t.trim()).filter(Boolean);
    if (!textList.length) { setError("Please enter at least one text."); setLoading(false); return; }
    try {
      const res = await fetch(`${API_BASE}/api/v1/detect/cross-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texts: textList, method, threshold, download_report: downloadReport, download_format: downloadFormat }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `cross_batch_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else { setResult(await res.json()); }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout title="Cross-Batch Detection" subtitle="Check submitted texts against all stored reference batches" icon="🗄️" color="#EC4899">
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Input Texts</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <TextAreaField label="Texts to Check (one per line)" value={texts} onChange={setTexts} placeholder={"Quick brown fox\nLazy dog jumps\nAnother entry here"} required />
            <div style={{ padding: "10px 14px", background: "#EC489914", border: "1px solid #EC489930", borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: "#EC4899", fontWeight: 500 }}>
                ℹ️ Register reference batches first via <a href="/register" style={{ color: "#DB2777" }}>the Register page</a> (backs onto <code>/api/v1/ingest/reference/register</code>) before running cross-batch checks.
              </p>
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Detection Method</h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <RadioGroup
              options={[
                { value: "exact", label: "Exact (SHA-256 hash)" },
                { value: "fuzzy", label: "Fuzzy (Levenshtein/Jaccard)" },
                { value: "semantic", label: "Semantic (SBERT cosine)" },
              ]}
              value={method}
              onChange={(v) => setMethod(v as Method)}
            />
            {method !== "exact" && (
              <SliderField label="Similarity Threshold" value={threshold} onChange={setThreshold} min={0.5} max={1.0} step={0.01} />
            )}
          </div>
        </div>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />
        <SubmitButton loading={loading} color="#EC4899" />
      </form>

      <ResultPanel result={result} error={error} color="#EC4899" renderResult={(r) => {
        const totalSubmitted = typeof r.total_submitted === "number" ? r.total_submitted : null;
        const totalReferences = typeof r.total_references === "number" ? r.total_references : null;
        const totalDuplicates = typeof r.total_duplicates === "number" ? r.total_duplicates : null;
        const methodUsed = typeof r.method === "string" ? r.method.toUpperCase() : "-";
        const results = Array.isArray(r.results) ? r.results : [];

        return (
          <>
            <ResultRow label="Total Submitted" value={String(totalSubmitted ?? "—")} />
            <ResultRow label="Total References Checked" value={String(totalReferences ?? "—")} />
            <ResultRow
              label="Duplicates Found"
              value={String(totalDuplicates ?? "—")}
              highlight={(totalDuplicates ?? 0) > 0}
            />
            <ResultRow label="Method Used" value={methodUsed} />

            {results.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <p style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>Per-Text Results:</p>
                {results.map((item: unknown, i: number) => {
                  const obj = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
                  const submittedText = typeof obj.submitted_text === "string" ? obj.submitted_text : "";
                  const isDuplicate = obj.is_duplicate === true;
                  const matchedBatchName = typeof obj.matched_batch_name === "string" ? obj.matched_batch_name : null;
                  const matchedBatchId = typeof obj.matched_batch_id === "string" ? obj.matched_batch_id : null;
                  const riskLevel = typeof obj.risk_level === "string" ? obj.risk_level : "";

                  return (
                    <div
                      key={i}
                      style={{
                        background: "var(--bg-secondary)",
                        borderRadius: 10,
                        padding: "12px 14px",
                        marginBottom: 8,
                        border: `1px solid ${isDuplicate ? "#EC489930" : "var(--border)"}`,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 13, color: "var(--text-secondary)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginRight: 10 }}>
                          {submittedText}
                        </span>
                        <span style={{ fontWeight: 700, fontSize: 13, flexShrink: 0, color: isDuplicate ? "#EF4444" : "#22C55E" }}>
                          {isDuplicate ? "DUP" : "CLEAN"}
                        </span>
                      </div>
                      {isDuplicate && (
                        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                          Matched in batch: <strong>{matchedBatchName ?? matchedBatchId ?? "—"}</strong> · Risk: {riskLevel || "—"}
                        </p>
                      )}
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
