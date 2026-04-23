"use client";

import { useState } from "react";
import AnalyzerLayout from "../AnalyzerLayout";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Scope = "global" | "batch-name" | "batch-id";

export default function ExactDetectPage() {
  const [text, setText] = useState("");
  const [scope, setScope] = useState<Scope>("global");
  const [batchId, setBatchId] = useState("");
  const [batchName, setBatchName] = useState("");
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("excel");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true); setResult(null); setError(null);

    try {
      const fd = new FormData();
      fd.append("text", text.trim());
      if (scope === "batch-id" && batchId) fd.append("batch_id", batchId.trim());
      if (scope === "batch-name" && batchName) fd.append("batch_name", batchName.trim());
      fd.append("download_report", downloadReport ? "true" : "false");
      fd.append("download_format", downloadFormat);

      const res = await fetch(`${API_BASE}/api/v1/detect/exact`, { method: "POST", body: fd });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Request failed"); }
      if (downloadReport) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `exact_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`; a.click();
        setResult({ downloaded: true });
      } else {
        setResult(await res.json());
      }
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <AnalyzerLayout
      title="Exact Duplicate Detection"
      subtitle="SHA-256 / MD5 hash-based byte-perfect comparison"
      icon="🔗"
      color="#6366F1"
    >
      <form onSubmit={handleSubmit}>
        <FormSection title="Input Text">
          <TextAreaField
            label="Text to Check"
            value={text}
            onChange={setText}
            placeholder="Paste your text here (typically < 20 words)..."
            required
          />
        </FormSection>

        <FormSection title="Search Scope">
          <RadioGroup
            options={[
              { value: "global", label: "Global (all stored texts)" },
              { value: "batch-name", label: "Specific batch (by name)" },
              { value: "batch-id", label: "Specific batch (by UUID)" },
            ]}
            value={scope}
            onChange={(v) => setScope(v as Scope)}
          />
          {scope === "batch-name" && (
            <InputField label="Batch Name" value={batchName} onChange={setBatchName} placeholder="e.g. Q1-2024-dataset" />
          )}
          {scope === "batch-id" && (
            <InputField label="Batch UUID" value={batchId} onChange={setBatchId} placeholder="e.g. 550e8400-e29b-41d4-a716-..." />
          )}
        </FormSection>

        <ReportSection downloadReport={downloadReport} setDownloadReport={setDownloadReport} downloadFormat={downloadFormat} setDownloadFormat={setDownloadFormat} />

        <SubmitButton loading={loading} color="#6366F1" />
      </form>

      <ResultPanel result={result} error={error} color="#6366F1" renderResult={(r) => (
        <ResultRow label="Duplicate Found" value={r.is_duplicate ? "✅ YES — Duplicate detected" : "🟢 CLEAN — No duplicate found"} highlight={r.is_duplicate} />
      )} />
    </AnalyzerLayout>
  );
}

// ─── Shared UI Primitives ───────────────────────────────────────────
function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>{title}</h2>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px 20px" }}>
        {children}
      </div>
    </div>
  );
}

export function TextAreaField({ label, value, onChange, placeholder, required }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>{label}{required && <span style={{ color: "#EF4444", marginLeft: 4 }}>*</span>}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        rows={4}
        style={{
          width: "100%", borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg-secondary)",
          color: "var(--text-primary)", fontSize: 15, padding: "12px 14px", resize: "vertical", outline: "none",
          fontFamily: "inherit", transition: "border-color 0.2s", boxSizing: "border-box",
        }}
        onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
        onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
      />
    </div>
  );
}

export function InputField({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: "100%", borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg-secondary)",
          color: "var(--text-primary)", fontSize: 15, padding: "11px 14px", outline: "none",
          fontFamily: "inherit", transition: "border-color 0.2s", boxSizing: "border-box",
        }}
        onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
        onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
      />
    </div>
  );
}

export function RadioGroup({ options, value, onChange }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          style={{
            padding: "8px 16px", borderRadius: 8, cursor: "pointer", fontSize: 14, fontWeight: 500,
            border: `1.5px solid ${value === opt.value ? "var(--accent)" : "var(--border)"}`,
            background: value === opt.value ? "var(--accent-glow)" : "var(--bg-secondary)",
            color: value === opt.value ? "var(--accent)" : "var(--text-secondary)",
            transition: "all 0.15s",
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function SliderField({ label, value, onChange, min, max, step }: { label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
        <span>{label}</span>
        <span style={{ color: "var(--accent)", fontWeight: 700 }}>{value}</span>
      </label>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: "var(--accent)" }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
        <span>{min}</span><span>{max}</span>
      </div>
    </div>
  );
}

export function ReportSection({ downloadReport, setDownloadReport, downloadFormat, setDownloadFormat }: { downloadReport: boolean; setDownloadReport: (v: boolean) => void; downloadFormat: string; setDownloadFormat: (v: string) => void }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>Report Export (Optional)</h2>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px 20px" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", fontSize: 14, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 12 }}>
          <input type="checkbox" checked={downloadReport} onChange={(e) => setDownloadReport(e.target.checked)} style={{ width: 16, height: 16, accentColor: "var(--accent)" }} />
          Download report after analysis
        </label>
        {downloadReport && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {["excel", "csv", "both"].map((fmt) => (
              <button key={fmt} type="button" onClick={() => setDownloadFormat(fmt)} style={{
                padding: "7px 14px", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600, textTransform: "capitalize",
                border: `1.5px solid ${downloadFormat === fmt ? "var(--accent)" : "var(--border)"}`,
                background: downloadFormat === fmt ? "var(--accent-glow)" : "var(--bg-secondary)",
                color: downloadFormat === fmt ? "var(--accent)" : "var(--text-secondary)",
              }}>
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function SubmitButton({ loading, color }: { loading: boolean; color: string }) {
  return (
    <button
      type="submit"
      disabled={loading}
      style={{
        width: "100%", padding: "14px", borderRadius: 12, border: "none", cursor: loading ? "not-allowed" : "pointer",
        background: loading ? "var(--bg-accent)" : `linear-gradient(135deg, ${color}, ${color}bb)`,
        color: loading ? "var(--text-muted)" : "white",
        fontWeight: 700, fontSize: 16, transition: "all 0.2s",
        boxShadow: loading ? "none" : `0 4px 16px ${color}44`,
        marginBottom: 28,
      }}
    >
      {loading ? "⏳  Analyzing…" : "🔍  Run Detection"}
    </button>
  );
}

export function ResultPanel({ result, error, color, renderResult }: { result: any; error: string | null; color: string; renderResult: (r: any) => React.ReactNode }) {
  if (error) return (
    <div style={{ background: "#EF444418", border: "1px solid #EF444440", borderRadius: 14, padding: "20px" }}>
      <p style={{ color: "#EF4444", fontWeight: 600 }}>❌ Error: {error}</p>
    </div>
  );
  if (!result) return null;
  if (result.downloaded) return (
    <div style={{ background: "#22C55E18", border: "1px solid #22C55E40", borderRadius: 14, padding: "20px" }}>
      <p style={{ color: "#22C55E", fontWeight: 600 }}>✅ Report downloaded successfully!</p>
    </div>
  );
  return (
    <div style={{ background: "var(--bg-card)", border: `1px solid ${color}30`, borderRadius: 14, padding: "24px", boxShadow: `0 4px 20px ${color}15` }}>
      <h3 style={{ fontWeight: 700, color: "var(--text-primary)", marginBottom: 16, fontSize: 16 }}>Results</h3>
      {renderResult(result)}
      <details style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Raw JSON Response</summary>
        <pre style={{ marginTop: 10, fontSize: 12, background: "var(--bg-secondary)", padding: 14, borderRadius: 8, overflow: "auto", color: "var(--text-secondary)" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export function ResultRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 500 }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: highlight ? "#EF4444" : "#22C55E" }}>{value}</span>
    </div>
  );
}
