"use client";

import { useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import AnalyzerLayout from "./AnalyzerLayout";
import PreviewPanel from "../components/PreviewPanel";
import { InputField } from "./exact/page";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const CLEANED_EXCEL_ENDPOINT =
  process.env.NEXT_PUBLIC_CLEANED_EXCEL_ENDPOINT || `${API_BASE}/api/v1/reports/cleaned`;

// ── Client-side xlsx → sheet-data extraction ─────────────────────────────────
async function xlsxBlobToSheets(
  blob: Blob,
  filename: string,
): Promise<CleanedFilePreview> {
  const XLSX = await import("xlsx");
  const ab = await blob.arrayBuffer();
  const wb = XLSX.read(ab, { type: "array" });

  const sheets: CleanedFilePreview["sheets"] = [];
  let totalEntries = 0;

  for (const sheetName of wb.SheetNames) {
    const ws = wb.Sheets[sheetName];
    const matrix = XLSX.utils.sheet_to_json(ws, {
      header: 1,
      blankrows: false,
    }) as unknown[][];

    const limited = matrix.slice(0, 2001); // header + up to 2000 rows
    const headers = (limited[0] || []).map((h, i) =>
      String(h ?? "").trim() || `Column ${i + 1}`,
    );
    const rows = limited.slice(1).map((r) =>
      headers.map((_, i) => String((r as unknown[])[i] ?? "")),
    );
    const sheetEntries = rows.length;
    totalEntries += sheetEntries;
    sheets.push({
      sheet_name: sheetName,
      headers,
      rows,
      total_entries: sheetEntries,
    });
  }

  return { filename, total_entries: totalEntries, sheets };
}

async function blobToCleanedPayload(blob: Blob, isZip: boolean, baseFilename: string): Promise<CleanedPreviewPayload> {
  if (!isZip) {
    const filePreview = await xlsxBlobToSheets(blob, baseFilename);
    return {
      total_files: 1,
      total_entries: filePreview.total_entries,
      files: [filePreview],
    };
  }

  // ZIP: extract each xlsx entry
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(blob);
  const fileNames = Object.keys(zip.files).filter(
    (n) => !zip.files[n].dir && n.toLowerCase().endsWith(".xlsx"),
  );

  if (!fileNames.length) {
    return { total_files: 0, total_entries: 0, files: [], note: "No xlsx files found in zip." };
  }

  const files: CleanedFilePreview[] = [];
  let totalEntries = 0;

  for (const name of fileNames) {
    const entryBlob = await zip.files[name].async("blob");
    const filePreview = await xlsxBlobToSheets(entryBlob, name);
    totalEntries += filePreview.total_entries;
    files.push(filePreview);
  }

  return { total_files: files.length, total_entries: totalEntries, files };
}

type MethodsConfig = {
  exact: boolean;
  fuzzy: boolean;
  semantic: boolean;
  license_check: boolean;
  web_scan: boolean;
  ai_detection: boolean;
};

type PipelineRunResult = {
  pipeline_id: string;
  status: string;
  summary?: {
    total_entries?: number;
    flagged?: number;
    risk_breakdown?: Record<string, number>;
  };
  row_duplicates?: unknown[];
  cell_duplicates?: unknown[];
  web_ai_results?: unknown[];
};

type CleanedFilePreview = {
  filename: string;
  total_entries: number;
  sheets: Array<{
    sheet_name: string;
    headers: string[];
    rows: string[][];
    total_entries: number;
  }>;
};

type CleanedPreviewPayload = {
  total_files: number;
  total_entries: number;
  files: CleanedFilePreview[];
  note?: string;
};

type PreviewState =
  | { open: false }
  | {
    open: true;
    title: string;
    kind: "report" | "excel" | "cleaned";
    colorReport?: boolean;
    reportData?: PipelineRunResult | null;
    excelBlob?: Blob | null;
    excelFileName?: string;
    cleanedData?: CleanedPreviewPayload | null;
    download: () => Promise<void>;
    downloading: boolean;
  };

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let idx = 0;
  while (n >= 1024 && idx < units.length - 1) {
    n /= 1024;
    idx++;
  }
  return `${n.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function isAllowedInputExt(ext: string): boolean {
  return [".xlsx", ".xls", ".csv", ".txt", ".pdf"].includes(ext);
}

async function pdfToTextFile(pdf: File): Promise<File> {
  const pdfjsLib = (await import("pdfjs-dist")) as unknown as {
    GlobalWorkerOptions?: { workerSrc: string };
    getDocument: (src: { data: ArrayBuffer }) => {
      promise: Promise<{
        numPages: number;
        getPage: (pageNumber: number) => Promise<{
          getTextContent: () => Promise<{ items?: Array<{ str?: unknown }> }>;
        }>;
      }>;
    };
  };
  // Ensure worker is configured; pdfjs supports bundlers via URL worker.
  try {
    if (pdfjsLib.GlobalWorkerOptions) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
    }
  } catch {
    // Best-effort; some bundlers handle workers automatically.
  }

  const ab = await pdf.arrayBuffer();
  const doc = await pdfjsLib.getDocument({ data: ab }).promise;

  let text = "";
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const strings = (content.items || [])
      .map((it) => (typeof it?.str === "string" ? it.str : ""))
      .filter(Boolean);
    text += strings.join(" ") + "\n";
  }

  const blob = new Blob([text], { type: "text/plain" });
  const base = pdf.name.replace(/\.pdf$/i, "");
  return new File([blob], `${base}.txt`, { type: "text/plain" });
}

async function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function filenameFromResponse(res: Response, fallback: string): string {
  const disp = res.headers.get("content-disposition") || "";
  const match = disp.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const raw = match?.[1] || match?.[2];
  if (!raw) return fallback;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export default function AnalyzePage() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);

  const [webScan, setWebScan] = useState(true);
  const [aiDetection, setAiDetection] = useState(true);
  const [coloredReport, setColoredReport] = useState(false);

  const [targetColumn, setTargetColumn] = useState("");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PipelineRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [cleanedLoading, setCleanedLoading] = useState(false);

  const [preview, setPreview] = useState<PreviewState>({ open: false });

  const folderInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const supportedHint = ".xlsx, .csv, .pdf, .txt";

  const totalSize = useMemo(() => files.reduce((acc, f) => acc + (f.size || 0), 0), [files]);

  function addFiles(incoming: FileList | File[]) {
    const list = Array.from(incoming);
    const allowed: File[] = [];
    const rejected: File[] = [];

    for (const f of list) {
      const e = extOf(f.name);
      if (isAllowedInputExt(e)) allowed.push(f);
      else rejected.push(f);
    }

    if (rejected.length) {
      setError(`Ignored ${rejected.length} unsupported file(s). Supported: ${supportedHint}`);
    }

    if (!allowed.length) return;

    setFiles((prev) => {
      const next = [...prev];
      for (const f of allowed) {
        const key = `${f.name}__${f.size}__${f.lastModified}`;
        const exists = next.some((x) => `${x.name}__${x.size}__${x.lastModified}` === key);
        if (!exists) next.push(f);
      }
      return next;
    });
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function runPipeline() {
    if (!files.length) {
      setError("Please upload at least one file.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const methods: MethodsConfig = {
        exact: true,
        fuzzy: true,
        semantic: true,
        license_check: true,
        web_scan: webScan,
        ai_detection: aiDetection,
      };

      const fd = new FormData();

      // Convert PDFs to TXT on the client so the backend can process them.
      for (const f of files) {
        const e = extOf(f.name);
        if (e === ".pdf") {
          const txt = await pdfToTextFile(f);
          fd.append("files", txt);
        } else {
          fd.append("files", f);
        }
      }

      fd.append("methods", JSON.stringify(methods));
      fd.append("target_column", targetColumn.trim() ? targetColumn.trim() : "auto");
      fd.append("download_report", "false");
      fd.append("report_format", "excel");
      fd.append("color_report", coloredReport ? "true" : "false");

      const res = await fetch(`${API_BASE}/api/v1/pipeline/run`, {
        method: "POST",
        body: fd,
      });

      if (!res.ok) {
        let msg = "Pipeline execution failed";
        try {
          const d = await res.json();
          if (typeof d?.detail === "string") msg = d.detail;
          if (typeof d?.detail?.message === "string") msg = d.detail.message;
          if (Array.isArray(d?.detail?.available_columns)) {
            msg += ` Available columns: ${d.detail.available_columns.join(", ")}`;
          }
        } catch {
          // ignore
        }
        throw new Error(msg);
      }

      const data = (await res.json()) as PipelineRunResult;
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function openReportPreview() {
    if (!result) return;

    setPreview({
      open: true,
      title: coloredReport ? "Report Preview (Colored)" : "Report Preview",
      kind: "report",
      colorReport: coloredReport,
      reportData: result,
      excelBlob: null,
      excelFileName: undefined,
      downloading: false,
      download: async () => {
        setPreview((prev) => (prev.open ? { ...prev, downloading: true } : prev));
        try {
          const res = await fetch(`${API_BASE}/api/v1/reports/combined`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              ...result,
              color_report: coloredReport,
            }),
          });
          if (!res.ok) {
            let msg = "Failed to generate report";
            try {
              const d = await res.json();
              msg = d?.detail || msg;
            } catch { }
            throw new Error(msg);
          }
          const blob = await res.blob();
          await downloadBlob(blob, `pipeline_${result.pipeline_id.slice(0, 8)}_report.xlsx`);
        } finally {
          setPreview((prev) => (prev.open ? { ...prev, downloading: false } : prev));
        }
      },
    });
  }

  async function openCleanedPreview() {
    if (!result) return;

    // Only .xlsx files are supported for cleaned output
    const xlsxFiles = files.filter((f) => f.name.toLowerCase().endsWith(".xlsx"));
    if (!xlsxFiles.length) {
      setError("No .xlsx files found in your upload. Cleaned output only works with Excel (.xlsx) files.");
      return;
    }

    setCleanedLoading(true);
    setError(null);

    try {
      const fd = new FormData();
      for (const f of xlsxFiles) {
        fd.append("files", f);
      }
      fd.append("row_duplicates", JSON.stringify(result.row_duplicates ?? []));
      fd.append("cell_duplicates", JSON.stringify(result.cell_duplicates ?? []));
      fd.append("web_ai_results", JSON.stringify(result.web_ai_results ?? []));

      const res = await fetch(CLEANED_EXCEL_ENDPOINT, {
        method: "POST",
        body: fd,
      });

      if (!res.ok) {
        let msg = "Cleaned file endpoint failed";
        try {
          const d = await res.json();
          msg = d?.detail || msg;
        } catch { }
        throw new Error(msg);
      }

      const blob = await res.blob();
      const contentType = res.headers.get("content-type") ?? "";
      const isZip = contentType.includes("zip");
      const ext = isZip ? "zip" : "xlsx";
      const fileName = `pipeline_${result.pipeline_id.slice(0, 8)}_cleaned.${ext}`;

      // Parse blob client-side to build preview data
      const cleanedData = await blobToCleanedPayload(blob, isZip, fileName);

      setPreview({
        open: true,
        title: "Cleaned File Preview",
        kind: "cleaned",
        excelBlob: null,
        excelFileName: fileName,
        cleanedData,
        reportData: null,
        downloading: false,
        download: async () => {
          setPreview((prev) => (prev.open ? { ...prev, downloading: true } : prev));
          try {
            await downloadBlob(blob, fileName);
          } finally {
            setPreview((prev) => (prev.open ? { ...prev, downloading: false } : prev));
          }
        },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to generate cleaned file";
      setError(msg);
    } finally {
      setCleanedLoading(false);
    }
  }

  async function downloadCleanedFile() {
    if (!result) return;
    const xlsxFiles = files.filter((f) => f.name.toLowerCase().endsWith(".xlsx"));
    if (!xlsxFiles.length) {
      setError("No .xlsx files found in your upload. Cleaned output only works with Excel (.xlsx) files.");
      return;
    }

    setCleanedLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      for (const f of xlsxFiles) fd.append("files", f);
      fd.append("row_duplicates", JSON.stringify(result.row_duplicates ?? []));
      fd.append("cell_duplicates", JSON.stringify(result.cell_duplicates ?? []));
      fd.append("web_ai_results", JSON.stringify(result.web_ai_results ?? []));

      const res = await fetch(CLEANED_EXCEL_ENDPOINT, { method: "POST", body: fd });
      if (!res.ok) {
        let msg = "Cleaned file endpoint failed";
        try { const d = await res.json(); msg = d?.detail || msg; } catch { }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const isZip = (res.headers.get("content-type") ?? "").includes("zip");
      const ext = isZip ? "zip" : "xlsx";
      await downloadBlob(blob, `pipeline_${result.pipeline_id.slice(0, 8)}_cleaned.${ext}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to download cleaned file");
    } finally {
      setCleanedLoading(false);
    }
  }

  return (
    <AnalyzerLayout
      title="Plagiarism Scan"
      subtitle="Upload files or folders, run the unified pipeline, preview results, then download"
      icon="🧪"
      color="#6366F1"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void runPipeline();
        }}
      >
        {/* Upload */}
        <Section title="File & Folder Input">
          <div
            onDragEnter={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragActive(true);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragActive(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragActive(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragActive(false);
              if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
            }}
            style={{
              border: `2px dashed ${dragActive ? "var(--accent)" : "var(--border)"}`,
              background: dragActive ? "var(--accent-glow)" : "var(--bg-secondary)",
              borderRadius: 14,
              padding: "18px",
              transition: "all var(--transition)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div>
                <p style={{ fontSize: 14, fontWeight: 900, color: "var(--text-primary)" }}>Drag & drop files here</p>
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>Supported: {supportedHint}</p>
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  style={primaryButtonStyle()}
                >
                  Browse Files
                </button>
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  style={secondaryButtonStyle()}
                >
                  Browse Folder
                </button>
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".xlsx,.xls,.csv,.txt,.pdf"
              style={{ display: "none" }}
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            <input
              ref={folderInputRef}
              type="file"
              multiple
              // @ts-expect-error nonstandard directory upload attribute
              webkitdirectory=""
              style={{ display: "none" }}
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            {files.length > 0 && (
              <div style={{ marginTop: 14, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
                <div style={{ padding: "10px 12px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <p style={{ fontSize: 13, fontWeight: 900, color: "var(--text-primary)" }}>
                    Selected Files ({files.length}) · {formatBytes(totalSize)}
                  </p>
                  <button type="button" onClick={() => setFiles([])} style={{ background: "none", border: "none", color: "#EF4444", fontWeight: 900, cursor: "pointer", fontSize: 12 }}>
                    Clear
                  </button>
                </div>
                <div style={{ maxHeight: 220, overflow: "auto" }}>
                  {files.map((f, idx) => (
                    <div key={`${f.name}-${f.size}-${f.lastModified}-${idx}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "10px 12px", borderBottom: idx === files.length - 1 ? "none" : "1px solid var(--border)" }}>
                      <div style={{ minWidth: 0 }}>
                        <p style={{ fontSize: 13, fontWeight: 800, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.webkitRelativePath || f.name}>
                          {f.webkitRelativePath || f.name}
                        </p>
                        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{formatBytes(f.size)}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeFile(idx)}
                        aria-label={`Remove ${f.name}`}
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: 10,
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: "var(--text-secondary)",
                          cursor: "pointer",
                          fontWeight: 900,
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* Options */}
        <Section title="Controls">
          <div style={{ display: "grid", gap: 12 }}>
            <CheckboxRow
              label="Web Scan"
              description="Scan the web for matches"
              checked={webScan}
              onChange={setWebScan}
            />
            <CheckboxRow
              label="AI Detection"
              description="Enable AI-assisted analysis"
              checked={aiDetection}
              onChange={setAiDetection}
            />
            <CheckboxRow
              label="Colored Report"
              description="Include color-coded highlights in the downloaded report"
              checked={coloredReport}
              onChange={setColoredReport}
            />
          </div>
        </Section>

        {/* Column */}
        <Section title="Column Specification">
          <InputField
            label="Query Column"
            value={targetColumn}
            onChange={setTargetColumn}
            placeholder="Auto (recommended)"
          />
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            Use this if your file doesn’t have a default query column. Leave blank for auto-detect.
          </p>
        </Section>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%",
            padding: "14px",
            borderRadius: 12,
            border: "none",
            cursor: loading ? "not-allowed" : "pointer",
            background: loading ? "var(--bg-accent)" : "linear-gradient(135deg, var(--accent), var(--accent-2))",
            color: loading ? "var(--text-muted)" : "white",
            fontWeight: 900,
            fontSize: 16,
            transition: "all var(--transition)",
            boxShadow: loading ? "none" : "0 10px 30px var(--accent-glow)",
            marginBottom: 18,
          }}
        >
          {loading ? "⏳ Analyzing…" : "Run Scan"}
        </button>

        {error && (
          <div style={{ background: "#EF444418", border: "1px solid #EF444440", borderRadius: 14, padding: "16px", marginBottom: 18 }}>
            <p style={{ color: "#EF4444", fontWeight: 800 }}>Error: {error}</p>
          </div>
        )}

        {result && (
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div>
                <p style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.6 }}>Results</p>
                <p style={{ fontSize: 16, fontWeight: 900, color: "var(--text-primary)", marginTop: 4 }}>Pipeline {result.pipeline_id.slice(0, 8)} · {result.status.toUpperCase()}</p>
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 6 }}>
                  Total entries: {String(result.summary?.total_entries ?? "—")} · Flagged: {String(result.summary?.flagged ?? "—")}
                </p>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="button" onClick={() => void openReportPreview()} style={primaryButtonStyle()}>
                  Preview Report
                </button>
                <button
                  type="button"
                  onClick={() => void openCleanedPreview()}
                  disabled={cleanedLoading}
                  style={{
                    ...secondaryButtonStyle(),
                    opacity: cleanedLoading ? 0.7 : 1,
                    cursor: cleanedLoading ? "not-allowed" : "pointer",
                  }}
                >
                  {cleanedLoading ? "Parsing…" : "Preview Cleaned File"}
                </button>
                <button
                  type="button"
                  onClick={() => void downloadCleanedFile()}
                  disabled={cleanedLoading}
                  style={{
                    ...secondaryButtonStyle(),
                    opacity: cleanedLoading ? 0.7 : 1,
                    cursor: cleanedLoading ? "not-allowed" : "pointer",
                  }}
                >
                  Download Cleaned
                </button>
              </div>
            </div>

            <details style={{ marginTop: 14 }}>
              <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)", fontWeight: 800 }}>Raw JSON</summary>
              <pre style={{ marginTop: 10, fontSize: 12, background: "var(--bg-secondary)", padding: 14, borderRadius: 10, overflow: "auto", color: "var(--text-secondary)" }}>
                {JSON.stringify(result, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </form>

      {preview.open && (
        <PreviewPanel
          key={`${preview.kind}:${preview.title}`}
          open
          title={preview.title}
          kind={preview.kind}
          colorReport={preview.colorReport}
          reportData={preview.reportData}
          excelBlob={preview.excelBlob}
          excelFileName={preview.excelFileName}
          cleanedData={"cleanedData" in preview ? preview.cleanedData : null}
          downloading={preview.downloading}
          onDownload={preview.download}
          onClose={() => setPreview({ open: false })}
        />
      )}
    </AnalyzerLayout>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <h2 style={{ fontSize: 13, fontWeight: 900, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 12 }}>{title}</h2>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "18px" }}>
        {children}
      </div>
    </div>
  );
}

function CheckboxRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      style={{
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        padding: "12px",
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--bg-secondary)",
        cursor: "pointer",
        transition: "all var(--transition)",
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, accentColor: "var(--accent)", marginTop: 2 }}
      />
      <span style={{ display: "block" }}>
        <span style={{ display: "block", fontSize: 14, fontWeight: 900, color: "var(--text-primary)" }}>{label}</span>
        <span style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{description}</span>
      </span>
    </label>
  );
}

function primaryButtonStyle(): CSSProperties {
  return {
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid transparent",
    background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
    color: "white",
    fontWeight: 900,
    cursor: "pointer",
    transition: "all var(--transition)",
    boxShadow: "0 10px 25px var(--accent-glow)",
  };
}

function secondaryButtonStyle(): CSSProperties {
  return {
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid var(--border)",
    background: "var(--bg-secondary)",
    color: "var(--text-primary)",
    fontWeight: 900,
    cursor: "pointer",
    transition: "all var(--transition)",
  };
}
