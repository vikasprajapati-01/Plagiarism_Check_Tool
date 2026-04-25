"use client";

import { useState, useRef } from "react";
import AnalyzerLayout from "../AnalyzerLayout";
import { ReportSection, SubmitButton, ResultPanel, ResultRow } from "../exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function FolderUploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [downloadReport, setDownloadReport] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState("excel");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const folderInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
  };


  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("Please select a folder or archive first.");
      return;
    }
    setLoading(true);
    setResult(null);
    setError(null);

    const fd = new FormData();
    files.forEach((f) => {
      fd.append("files", f);
    });

    const methodsData = {
      exact: true,
      fuzzy: true,
      semantic: true,
      ai_detection: true,
      web_scan: true,
      license_check: true
    };
    fd.append("methods", JSON.stringify(methodsData));
    
    fd.append("download_report", downloadReport ? "true" : "false");
    fd.append("download_format", downloadFormat);

    try {
      const res = await fetch(`${API_BASE}/api/v1/pipeline/run`, {
        method: "POST",
        body: fd,
      });

      if (!res.ok) {
        let errMessage = "Pipeline execution failed";
        try {
            const d = await res.json();
            errMessage = d.detail || errMessage;
        } catch (_) {}
        throw new Error(errMessage);
      }

      if (downloadReport) {
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
           setResult(await res.json());
        } else {
           const blob = await res.blob();
           const url = URL.createObjectURL(blob);
           const a = document.createElement("a");
           a.href = url;
           a.download = `pipeline_report.${downloadFormat === "csv" ? "csv" : "xlsx"}`;
           a.click();
           setResult({ downloaded: true });
        }
      } else {
        setResult(await res.json());
      }

    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnalyzerLayout
      title="Full Folder Scan"
      subtitle="Run the entire unified pipeline on multiple files"
      icon="📁"
      color="#14B8A6"
    >
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 14 }}>
            Input Source
          </h2>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px" }}>
            <div style={{ display: "flex", gap: 14, marginBottom: 16 }}>
              <button
                type="button"
                onClick={() => folderInputRef.current?.click()}
                style={{
                  flex: 1, padding: "20px 16px", borderRadius: 10, border: "2px dashed #14B8A650",
                  background: "#14B8A60a", color: "#14B8A6", fontWeight: 600, cursor: "pointer",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
                  transition: "all 0.15s"
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#14B8A615")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#14B8A60a")}
              >
                <span style={{ fontSize: 24 }}>📁</span>
                Select a Folder
              </button>
            </div>
            
            <input
              type="file"
              // @ts-ignore
              webkitdirectory=""
              ref={folderInputRef}
              style={{ display: "none" }}
              onChange={handleFolderSelect}
            />


            {files.length > 0 && (
              <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: "12px", border: "1px solid var(--border)", maxHeight: 200, overflowY: "auto" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "8px", marginBottom: "8px", borderBottom: "1px solid var(--border)" }}>
                  <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)" }}>
                    Ready to scan {files.length} file(s):
                  </p>
                  <button type="button" onClick={() => setFiles([])} style={{ fontSize: 12, background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontWeight: 600 }}>
                    Clear All
                  </button>
                </div>
                {files.map((file, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--text-secondary)", padding: "4px 0" }}>
                     <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{file.webkitRelativePath || file.name}</span>
                     <button type="button" onClick={() => removeFile(i)} style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", opacity: 0.7 }}>✕</button>
                  </div>
                ))}
              </div>
            )}
            
            <div style={{ marginTop: 14, padding: "10px 14px", background: "#14B8A614", border: "1px solid #14B8A630", borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: "#0F766E", fontWeight: 500 }}>
                 ℹ️ **Supported Formats:** .csv, .xlsx, .xls, .txt. <br/>
                 Any unsupported files in the folder will be safely ignored.
              </p>
            </div>
          </div>
        </div>

        <ReportSection
          downloadReport={downloadReport}
          setDownloadReport={setDownloadReport}
          downloadFormat={downloadFormat}
          setDownloadFormat={setDownloadFormat}
        />

        <SubmitButton loading={loading} color="#14B8A6" />
      </form>

      <ResultPanel
        result={result}
        error={error}
        color="#14B8A6"
        renderResult={(r) => {
          if (r.downloaded) return null;
          const { summary } = r;
          if (!summary) return null;
          return (
            <>
              <ResultRow label="Status" value={r.status.toUpperCase()} highlight={false} />
              <ResultRow label="Total Entries Analysed" value={String(summary.total_entries)} />
              <ResultRow label="Total Flagged Elements" value={String(summary.flagged)} highlight={summary.flagged > 0} />
              <div style={{ marginTop: 14 }}>
                 <p style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>Risk Breakdown:</p>
                 <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "stretch" }}>
                   <Badge label="High Risk" count={summary.risk_breakdown?.high || 0} color="#EF4444" />
                   <Badge label="Medium Risk" count={summary.risk_breakdown?.medium || 0} color="#F59E0B" />
                   <Badge label="Low Risk" count={summary.risk_breakdown?.low || 0} color="#3B82F6" />
                   <Badge label="No Risk" count={summary.risk_breakdown?.none || 0} color="#10B981" />
                 </div>
              </div>
            </>
          );
        }}
      />
    </AnalyzerLayout>
  );
}

function Badge({ label, count, color }: { label: string, count: number, color: string }) {
  return (
    <div style={{ flex: "1 1 0", padding: "12px 10px", borderRadius: 8, background: `${color}15`, border: `1px solid ${color}30`, textAlign: "center", minWidth: 80 }}>
      <p style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 20, fontWeight: 800, color: color }}>{count}</p>
    </div>
  );
}
