"use client";

import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

type PreviewKind = "report" | "excel";

type ReportLike = {
  pipeline_id: string;
  status?: string;
  summary?: unknown;
  row_duplicates?: unknown[];
  cell_duplicates?: unknown[];
  web_ai_results?: unknown[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export type PreviewPanelProps = {
  open: boolean;
  title: string;
  kind: PreviewKind;
  colorReport?: boolean;

  reportData?: ReportLike | null;

  excelBlob?: Blob | null;
  excelFileName?: string;

  downloading?: boolean;
  onDownload: () => void | Promise<void>;
  onClose: () => void;
};

function clampArray<T>(arr: T[], max: number): T[] {
  if (arr.length <= max) return arr;
  return arr.slice(0, max);
}

function safeNumber(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function getRowBgForDuplicateType(typeValue: unknown, colorReport: boolean): string {
  if (!colorReport) return "transparent";
  const t = String(typeValue ?? "").toLowerCase();
  if (t === "exact") return "rgba(239, 68, 68, 0.12)";
  if (t === "near") return "rgba(245, 158, 11, 0.14)";
  return "transparent";
}

function getRowBgForPlagiarised(plagiarised: unknown, colorReport: boolean): string {
  if (!colorReport) return "transparent";
  const p = String(plagiarised ?? "").toLowerCase();
  if (p === "yes") return "rgba(239, 68, 68, 0.12)";
  if (p === "no") return "rgba(34, 197, 94, 0.12)";
  return "transparent";
}

function getCellBgForAiPct(aiPct: unknown, colorReport: boolean): string {
  if (!colorReport) return "transparent";
  const v = safeNumber(aiPct);
  if (v >= 80) return "rgba(239, 68, 68, 0.18)";
  if (v >= 50) return "rgba(245, 158, 11, 0.18)";
  if (v >= 20) return "rgba(234, 179, 8, 0.18)";
  return "transparent";
}

type SheetPreview = {
  sheetNames: string[];
  activeSheet: string;
  headers: string[];
  rows: Array<Record<string, string>>;
};

async function parseExcelBlob(blob: Blob): Promise<SheetPreview> {
  // Lazy import so this file doesn’t increase initial bundle size.
  const XLSX = await import("xlsx");

  const ab = await blob.arrayBuffer();
  const wb = XLSX.read(ab, { type: "array" });

  const sheetNames = wb.SheetNames || [];
  const activeSheet = sheetNames[0] || "";

  const sheet = activeSheet ? wb.Sheets[activeSheet] : undefined;
  const matrix: unknown[][] = sheet
    ? (XLSX.utils.sheet_to_json(sheet, { header: 1, blankrows: false }) as unknown[][])
    : [];

  const limited = clampArray(matrix, 2001); // header + 2000 rows
  const firstRow = limited[0] || [];
  const headers = firstRow.map((h: unknown, idx: number) => (String(h ?? "").trim() || `Column ${idx + 1}`));

  const rows = limited.slice(1).map((r: unknown[]) => {
    const obj: Record<string, string> = {};
    headers.forEach((h, i) => {
      obj[h] = String(r?.[i] ?? "");
    });
    return obj;
  });

  return { sheetNames, activeSheet, headers, rows };
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "8px 12px",
        borderRadius: 10,
        border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
        background: active ? "var(--accent-glow)" : "var(--bg-secondary)",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        fontSize: 13,
        fontWeight: 700,
        cursor: "pointer",
        transition: "all var(--transition)",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

function MiniSpinner() {
  return (
    <span
      aria-hidden
      style={{
        width: 14,
        height: 14,
        borderRadius: 999,
        border: "2px solid var(--border)",
        borderTopColor: "var(--accent)",
        display: "inline-block",
        animation: "spin-slow 0.9s linear infinite",
      }}
    />
  );
}

export default function PreviewPanel({
  open,
  title,
  kind,
  colorReport = false,
  reportData,
  excelBlob,
  excelFileName,
  downloading = false,
  onDownload,
  onClose,
}: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<string>(() => (kind === "report" ? "Summary" : "Preview"));

  const [excelState, setExcelState] = useState<{
    loading: boolean;
    error: string | null;
    sheetNames: string[];
    activeSheet: string;
    headers: string[];
    rows: Array<Record<string, string>>;
  }>({ loading: false, error: null, sheetNames: [], activeSheet: "", headers: [], rows: [] });

  const [page, setPage] = useState(1);
  const pageSize = 25;

  const totalPages = useMemo(() => {
    const total = excelState.rows.length;
    return Math.max(1, Math.ceil(total / pageSize));
  }, [excelState.rows.length]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!open) return;
      if (kind !== "excel") return;
      if (!excelBlob) {
        setExcelState((s) => ({ ...s, error: "No file to preview." }));
        return;
      }

      setExcelState({ loading: true, error: null, sheetNames: [], activeSheet: "", headers: [], rows: [] });
      try {
        const parsed = await parseExcelBlob(excelBlob);
        if (cancelled) return;
        setExcelState({
          loading: false,
          error: null,
          sheetNames: parsed.sheetNames,
          activeSheet: parsed.activeSheet,
          headers: parsed.headers,
          rows: parsed.rows,
        });
      } catch (e: unknown) {
        if (cancelled) return;
        setExcelState({ loading: false, error: e instanceof Error ? e.message : "Failed to parse Excel file.", sheetNames: [], activeSheet: "", headers: [], rows: [] });
      }
    }

    run();

    return () => {
      cancelled = true;
    };
  }, [open, kind, excelBlob]);

  const reportTabs = ["Summary", "Row Matches", "Cell Matches", "Web / AI"];

  const visibleExcelRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    const end = start + pageSize;
    return excelState.rows.slice(start, end);
  }, [excelState.rows, page]);

  if (!open) return null;

  const overlayStyle: CSSProperties = {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.35)",
    backdropFilter: "blur(6px)",
    zIndex: 2000,
    display: "flex",
    justifyContent: "flex-end",
  };

  const panelStyle: CSSProperties = {
    width: "min(860px, 100vw)",
    height: "100%",
    background: "var(--bg-primary)",
    borderLeft: "1px solid var(--border)",
    boxShadow: "var(--shadow-lg)",
    display: "flex",
    flexDirection: "column",
    transform: "translateX(0)",
    transition: "transform var(--transition)",
  };

  const headerStyle: CSSProperties = {
    padding: "18px 18px",
    borderBottom: "1px solid var(--border)",
    background: "var(--bg-secondary)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  };

  const buttonStyle: CSSProperties = {
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid var(--border)",
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    cursor: "pointer",
    fontWeight: 800,
    transition: "all var(--transition)",
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={overlayStyle}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div style={panelStyle}>
        <div style={headerStyle}>
          <div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.6 }}>Preview</p>
            <h3 style={{ fontSize: 16, fontWeight: 900, color: "var(--text-primary)", letterSpacing: "-0.3px" }}>{title}</h3>
            {kind === "excel" && excelFileName && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{excelFileName}</p>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              type="button"
              onClick={onDownload}
              disabled={downloading}
              style={{
                ...buttonStyle,
                background: downloading ? "var(--bg-accent)" : "linear-gradient(135deg, var(--accent), var(--accent-2))",
                color: downloading ? "var(--text-muted)" : "white",
                borderColor: downloading ? "var(--border)" : "transparent",
                boxShadow: downloading ? "none" : "0 8px 20px var(--accent-glow)",
              }}
            >
              {downloading ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                  <MiniSpinner /> Generating…
                </span>
              ) : (
                "Download"
              )}
            </button>
            <button type="button" onClick={onClose} style={buttonStyle}>
              Close Preview
            </button>
          </div>
        </div>

        {/* Tabs */}
        {kind === "report" && (
          <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, flexWrap: "wrap" }}>
            {reportTabs.map((t) => (
              <TabButton key={t} active={activeTab === t} label={t} onClick={() => setActiveTab(t)} />
            ))}
          </div>
        )}

        <div style={{ padding: "18px", overflow: "auto", flex: 1 }}>
          {kind === "report" ? (
            <ReportPreview activeTab={activeTab} data={reportData} colorReport={colorReport} />
          ) : (
            <ExcelPreview
              state={excelState}
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              visibleRows={visibleExcelRows}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ReportPreview({
  activeTab,
  data,
  colorReport,
}: {
  activeTab: string;
  data?: ReportLike | null;
  colorReport: boolean;
}) {
  if (!data) {
    return (
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 18,
        color: "var(--text-secondary)",
      }}>
        No report data available.
      </div>
    );
  }

  const summary = data.summary || {};
  const summaryObj = isRecord(summary) ? summary : {};
  const rows = Array.isArray(data.row_duplicates) ? data.row_duplicates.filter(isRecord) : [];
  const cells = Array.isArray(data.cell_duplicates) ? data.cell_duplicates.filter(isRecord) : [];
  const webAi = Array.isArray(data.web_ai_results) ? data.web_ai_results.filter(isRecord) : [];

  if (activeTab === "Summary") {
    return (
      <div style={{ display: "grid", gap: 14 }}>
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: 18,
        }}>
          <p style={{ fontSize: 12, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Run</p>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 10 }}>
            <SummaryStat label="Pipeline ID" value={String(data.pipeline_id || "—")} />
            <SummaryStat label="Status" value={String(data.status || "—").toUpperCase()} />
          </div>
        </div>

        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: 18,
        }}>
          <p style={{ fontSize: 12, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Summary</p>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 10 }}>
            <SummaryStat label="Total Entries" value={String(summaryObj["total_entries"] ?? "—")} />
            <SummaryStat label="Flagged" value={String(summaryObj["flagged"] ?? "—")} />
            <SummaryStat label="Row Matches" value={String(rows.length)} />
            <SummaryStat label="Cell Matches" value={String(cells.length)} />
            <SummaryStat label="Web/AI Results" value={String(webAi.length)} />
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
            {colorReport ? "Colored preview is enabled." : "Colored preview is off."}
          </p>
        </div>
      </div>
    );
  }

  if (activeTab === "Row Matches") {
    return (
      <SimpleTable
        title={`Row-to-Row (${rows.length})`}
        columns={["original", "duplicate", "type", "similarity_pct"]}
        rows={rows}
        rowStyle={(r) => ({ background: getRowBgForDuplicateType(r["type"], colorReport) })}
      />
    );
  }

  if (activeTab === "Cell Matches") {
    return (
      <SimpleTable
        title={`Cell-to-Cell (${cells.length})`}
        columns={["original", "duplicate", "type", "similarity_pct"]}
        rows={cells}
        rowStyle={(r) => ({ background: getRowBgForDuplicateType(r["type"], colorReport) })}
      />
    );
  }

  return (
    <SimpleTable
      title={`AI-Plagiarism (${webAi.length})`}
      columns={["original", "plagiarised", "source", "ai_detected_pct"]}
      rows={webAi}
      rowStyle={(r) => ({ background: getRowBgForPlagiarised(r["plagiarised"], colorReport) })}
      cellStyle={(col, r) => {
        if (col === "ai_detected_pct") {
          return { background: getCellBgForAiPct(r["ai_detected_pct"], colorReport) };
        }
        return {};
      }}
    />
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 160 }}>
      <p style={{ fontSize: 12, fontWeight: 800, color: "var(--text-muted)" }}>{label}</p>
      <p style={{ fontSize: 14, fontWeight: 800, color: "var(--text-primary)", marginTop: 2, wordBreak: "break-word" }}>{value}</p>
    </div>
  );
}

function SimpleTable({
  title,
  columns,
  rows,
  rowStyle,
  cellStyle,
}: {
  title: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  rowStyle?: (row: Record<string, unknown>) => React.CSSProperties;
  cellStyle?: (col: string, row: Record<string, unknown>) => React.CSSProperties;
}) {
  const limited = clampArray(rows, 300);
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 14,
      overflow: "hidden",
    }}>
      <div style={{ padding: 14, borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
        <p style={{ fontSize: 13, fontWeight: 900, color: "var(--text-primary)" }}>{title}</p>
        {rows.length > limited.length && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            Showing first {limited.length} rows for performance.
          </p>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c}
                  style={{
                    textAlign: "left",
                    padding: "10px 12px",
                    color: "var(--text-secondary)",
                    fontWeight: 900,
                    borderBottom: "1px solid var(--border)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {limited.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{ padding: 14, color: "var(--text-muted)" }}>
                  No rows.
                </td>
              </tr>
            ) : (
              limited.map((r, idx) => (
                <tr key={idx} style={{ borderBottom: "1px solid var(--border)", ...(rowStyle?.(r) || {}) }}>
                  {columns.map((c) => (
                    <td
                      key={c}
                      style={{
                        padding: "10px 12px",
                        color: "var(--text-primary)",
                        verticalAlign: "top",
                        ...(cellStyle?.(c, r) || {}),
                      }}
                    >
                      <span style={{ display: "inline-block", maxWidth: 520, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={String(r[c] ?? "")}
                      >
                        {String(r[c] ?? "")}
                      </span>
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExcelPreview({
  state,
  page,
  totalPages,
  onPageChange,
  visibleRows,
}: {
  state: {
    loading: boolean;
    error: string | null;
    sheetNames: string[];
    activeSheet: string;
    headers: string[];
    rows: Array<Record<string, string>>;
  };
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
  visibleRows: Array<Record<string, string>>;
}) {
  if (state.loading) {
    return (
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 18,
        color: "var(--text-secondary)",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}>
        <MiniSpinner /> Parsing spreadsheet…
      </div>
    );
  }

  if (state.error) {
    return (
      <div style={{ background: "#EF444418", border: "1px solid #EF444440", borderRadius: 14, padding: 18 }}>
        <p style={{ color: "#EF4444", fontWeight: 800 }}>Preview error: {state.error}</p>
      </div>
    );
  }

  if (!state.headers.length) {
    return (
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 18,
        color: "var(--text-secondary)",
      }}>
        No rows to preview.
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <p style={{ fontSize: 13, fontWeight: 900, color: "var(--text-primary)" }}>Spreadsheet Preview</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            style={{
              padding: "8px 10px",
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--bg-secondary)",
              color: "var(--text-secondary)",
              cursor: page <= 1 ? "not-allowed" : "pointer",
              fontWeight: 800,
            }}
          >
            Prev
          </button>
          <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 800 }}>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            style={{
              padding: "8px 10px",
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--bg-secondary)",
              color: "var(--text-secondary)",
              cursor: page >= totalPages ? "not-allowed" : "pointer",
              fontWeight: 800,
            }}
          >
            Next
          </button>
        </div>
      </div>

      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        overflow: "hidden",
      }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                {state.headers.map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "10px 12px",
                      background: "var(--bg-secondary)",
                      borderBottom: "1px solid var(--border)",
                      color: "var(--text-secondary)",
                      fontWeight: 900,
                      whiteSpace: "nowrap",
                      position: "sticky",
                      top: 0,
                      zIndex: 1,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r, idx) => (
                <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                  {state.headers.map((h) => (
                    <td key={h} style={{ padding: "10px 12px", color: "var(--text-primary)", verticalAlign: "top" }}>
                      <span style={{ display: "inline-block", maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r[h] || ""}>
                        {r[h] || ""}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
        For performance, previews are limited to the first ~2000 rows.
      </p>
    </div>
  );
}
