"use client";

import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

type PreviewKind = "report" | "excel" | "cleaned";

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

function parseRowKey(label: string): [string, number] | null {
  if (!label) return null;
  const match = label.match(/-(?:Row\s+(\d+)|([A-Z]+)(\d+))$/);
  if (match) {
    const rowNum = parseInt(match[1] || match[3], 10);
    const prefix = label.slice(0, label.lastIndexOf(match[0]));
    return [prefix, rowNum];
  }
  return [label, 0];
}

function uniqueRowsFromPairs(pairs: Record<string, unknown>[], typeFilter?: string): Set<string> {
  const seen = new Set<string>();
  for (const pair of pairs) {
    if (typeFilter && String(pair["type"] || "") !== typeFilter) continue;
    for (const label of [String(pair["original"] || ""), String(pair["duplicate"] || "")]) {
      const key = parseRowKey(label);
      if (key) {
        seen.add(`${key[0]}__${key[1]}`);
      }
    }
  }
  return seen;
}

export type PreviewPanelProps = {
  open: boolean;
  title: string;
  kind: PreviewKind;
  colorReport?: boolean;

  reportData?: ReportLike | null;

  excelBlob?: Blob | null;
  excelFileName?: string;

  cleanedData?: {
    total_files: number;
    total_entries: number;
    files: Array<{
      filename: string;
      total_entries: number;
      sheets: Array<{
        sheet_name: string;
        headers: string[];
        rows: string[][];
        total_entries: number;
      }>;
    }>;
    note?: string;
  } | null;

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
  cleanedData,
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

  const reportTabs = ["Summary", "Row Matches", "Cell Matches", "Web / AI", "Risk Summary"];

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
          ) : kind === "excel" ? (
            <ExcelPreview
              state={excelState}
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              visibleRows={visibleExcelRows}
            />
          ) : (
            <CleanedPreview data={cleanedData} />
          )}
        </div>
      </div>
    </div>
  );
}

function CleanedPreview({
  data,
}: {
  data?: {
    total_files: number;
    total_entries: number;
    files: Array<{
      filename: string;
      total_entries: number;
      sheets: Array<{ sheet_name: string; headers: string[]; rows: string[][]; total_entries: number }>;
    }>;
    note?: string;
  } | null;
}) {
  if (!data || !Array.isArray(data.files) || data.files.length === 0) {
    return (
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 18,
        color: "var(--text-secondary)",
      }}>
        No cleaned preview available.
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 16,
      }}>
        <p style={{ fontSize: 12, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>
          Cleaned Summary
        </p>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 10 }}>
          <SummaryStat label="Files" value={String(data.total_files)} />
          <SummaryStat label="Total Unique Rows" value={String(data.total_entries)} />
        </div>
        {data.note && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>{data.note}</p>
        )}
      </div>

      {data.files.map((file) => (
        <div key={file.filename} style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          overflow: "hidden",
        }}>
          <div style={{ padding: 14, borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
            <p style={{ fontSize: 13, fontWeight: 900, color: "var(--text-primary)" }}>{file.filename}</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              Unique rows: {file.total_entries}
            </p>
          </div>
          <div style={{ padding: 14, display: "grid", gap: 12 }}>
            {file.sheets.map((sheet) => (
              <div key={sheet.sheet_name} style={{
                border: "1px solid var(--border)",
                borderRadius: 12,
                overflow: "hidden",
              }}>
                <div style={{ padding: 10, background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)" }}>
                  <p style={{ fontSize: 12, fontWeight: 800, color: "var(--text-secondary)" }}>
                    {sheet.sheet_name} · {sheet.total_entries} rows
                  </p>
                </div>
                {sheet.rows.length === 0 ? (
                  <div style={{ padding: 12 }}>
                    <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No rows after deduplication.</p>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          {sheet.headers.map((h) => (
                            <th
                              key={h}
                              style={{
                                textAlign: "left",
                                padding: "8px 10px",
                                background: "var(--bg-card)",
                                borderBottom: "1px solid var(--border)",
                                color: "var(--text-secondary)",
                                fontWeight: 800,
                                whiteSpace: "nowrap",
                              }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sheet.rows.map((row, idx) => (
                          <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                            {sheet.headers.map((_, colIdx) => (
                              <td key={colIdx} style={{ padding: "8px 10px", color: "var(--text-primary)" }}>
                                <span style={{ display: "inline-block", maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {row[colIdx] ?? ""}
                                </span>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
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
            <SummaryStat label="Total Files" value={String(summaryObj["total_files"] ?? "—")} />
            <SummaryStat label="Total Rows" value={String(summaryObj["total_rows"] ?? summaryObj["total_entries"] ?? "—")} />
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

  if (activeTab === "Risk Summary") {
    const totalRows = summaryObj["total_rows"] !== undefined
      ? safeNumber(summaryObj["total_rows"])
      : (summaryObj["total_entries"] !== undefined ? safeNumber(summaryObj["total_entries"]) : 0);

    const exactUniqueRows = uniqueRowsFromPairs(rows, "Exact");
    const nearUniqueRows = uniqueRowsFromPairs(rows, "Near");

    const aiUniqueRows = new Set<string>();
    for (const r of webAi) {
      if (safeNumber(r["ai_detected_pct"]) > 50.0) {
        const key = parseRowKey(String(r["original"] || ""));
        if (key) aiUniqueRows.add(`${key[0]}__${key[1]}`);
      }
    }

    const webUniqueRows = new Set<string>();
    for (const r of webAi) {
      if (String(r["plagiarised"] || "").trim().toLowerCase() === "yes") {
        const key = parseRowKey(String(r["original"] || ""));
        if (key) webUniqueRows.add(`${key[0]}__${key[1]}`);
      }
    }

    const exactPairs = rows.filter(r => r["type"] === "Exact").length;
    const nearPairs = rows.filter(r => r["type"] === "Near").length;
    const semanticPairs = 0;
    const aiPairs = webAi.filter(r => safeNumber(r["ai_detected_pct"]) > 50.0).length;
    const webPairs = webAi.filter(r => String(r["plagiarised"] || "").trim().toLowerCase() === "yes").length;
    const licensePairs = 0;

    const exactUnique = exactUniqueRows.size;
    const nearUnique = nearUniqueRows.size;
    const semanticUnique = 0;
    const aiUnique = aiUniqueRows.size;
    const webUnique = webUniqueRows.size;
    const licenseUnique = 0;

    const getRiskLevel = (flaggedUnique: number, total: number): [string, string, string] => {
      if (total <= 0) return ["Clean", "rgba(34, 197, 94, 0.15)", "#22C55E"];
      const pct = flaggedUnique / total * 100;
      if (pct === 0) return ["Clean", "rgba(34, 197, 94, 0.15)", "#22C55E"];
      if (pct <= 5) return ["Low", "rgba(34, 197, 94, 0.15)", "#22C55E"];
      if (pct <= 20) return ["Medium", "rgba(234, 179, 8, 0.18)", "#EAB308"];
      return ["High", "rgba(239, 68, 68, 0.18)", "#EF4444"];
    };

    const getFormattedRate = (flaggedUnique: number, total: number): string => {
      if (total <= 0) return "N/A";
      return `${(flaggedUnique / total * 100).toFixed(2)}%`;
    };

    const getRiskInfo = (unique: number, total: number) => {
      const [risk, bg, color] = getRiskLevel(unique, total);
      return { risk, bg, color };
    };

    const exactInfo = getRiskInfo(exactUnique, totalRows);
    const nearInfo = getRiskInfo(nearUnique, totalRows);
    const aiInfo = getRiskInfo(aiUnique, totalRows);
    const webInfo = getRiskInfo(webUnique, totalRows);

    const rowsData = [
      { method: "Exact Duplicate", pairs: exactPairs, unique: exactUnique, rate: getFormattedRate(exactUnique, totalRows), ...exactInfo },
      { method: "Near Duplicate", pairs: nearPairs, unique: nearUnique, rate: getFormattedRate(nearUnique, totalRows), ...nearInfo },
      { method: "Semantic Similar", pairs: semanticPairs, unique: semanticUnique, rate: totalRows > 0 ? "0.00%" : "N/A", risk: "Included in Near Duplicate", bg: "transparent", color: "var(--text-muted)" },
      { method: "AI Generated", pairs: aiPairs, unique: aiUnique, rate: getFormattedRate(aiUnique, totalRows), ...aiInfo },
      { method: "Web Plagiarised", pairs: webPairs, unique: webUnique, rate: getFormattedRate(webUnique, totalRows), ...webInfo },
      { method: "License Violation", pairs: licensePairs, unique: licenseUnique, rate: totalRows > 0 ? "0.00%" : "N/A", risk: "Not separately tracked", bg: "transparent", color: "var(--text-muted)" },
    ];

    const overallPairs = exactPairs + nearPairs + semanticPairs + aiPairs + webPairs + licensePairs;
    const overallUnion = new Set([...exactUniqueRows, ...nearUniqueRows, ...aiUniqueRows, ...webUniqueRows]);
    const overallUnique = overallUnion.size;
    const overallRate = getFormattedRate(overallUnique, totalRows);
    const [overallRisk, overallRiskBg, overallRiskColor] = getRiskLevel(overallUnique, totalRows);

    const totalForPrs = totalRows > 0 ? totalRows : 1;
    const exactRate = exactUnique / totalForPrs;
    const nearRate = nearUnique / totalForPrs;
    const semanticRate = 0.0;
    const aiRate = aiUnique / totalForPrs;
    const webRate = webUnique / totalForPrs;
    const licenseRate = 0.0;

    const rawPrs = (
      exactRate * 100.0 * 0.40 +
      nearRate * 100.0 * 0.20 +
      semanticRate * 100.0 * 0.15 +
      aiRate * 100.0 * 0.10 +
      webRate * 100.0 * 0.10 +
      licenseRate * 100.0 * 0.05
    );
    const prs = Math.round(Math.min(100.0, rawPrs) * 10) / 10;

    let prsBg = "rgba(34, 197, 94, 0.15)";
    let prsColor = "#22C55E";
    if (prs >= 60) {
      prsBg = "rgba(239, 68, 68, 0.18)";
      prsColor = "#EF4444";
    } else if (prs >= 40) {
      prsBg = "rgba(249, 115, 22, 0.18)";
      prsColor = "#F97316";
    } else if (prs >= 20) {
      prsBg = "rgba(234, 179, 8, 0.18)";
      prsColor = "#EAB308";
    }

    let qaText = "LOW RISK — Dataset appears clean for training use.";
    let qaColor = "#22C55E";
    let qaBg = "rgba(34, 197, 94, 0.08)";
    let qaBorder = "rgba(34, 197, 94, 0.2)";
    if (prs >= 60) {
      qaText = "CRITICAL RISK — Dataset has serious quality issues. Do not use for training without cleaning.";
      qaColor = "#EF4444";
      qaBg = "rgba(239, 68, 68, 0.08)";
      qaBorder = "rgba(239, 68, 68, 0.2)";
    } else if (prs >= 40) {
      qaText = "HIGH RISK — Significant issues found. Cleaning recommended before training.";
      qaColor = "#F97316";
      qaBg = "rgba(249, 115, 22, 0.08)";
      qaBorder = "rgba(249, 115, 22, 0.2)";
    } else if (prs >= 20) {
      qaText = "MEDIUM RISK — Minor issues found. Review flagged entries before training.";
      qaColor = "#EAB308";
      qaBg = "rgba(234, 179, 8, 0.08)";
      qaBorder = "rgba(234, 179, 8, 0.2)";
    }

    const s4ThStyle: React.CSSProperties = {
      textAlign: "center",
      padding: "10px 12px",
      color: "var(--text-secondary)",
      fontWeight: 900,
      borderBottom: "1px solid var(--border)",
      whiteSpace: "nowrap"
    };

    const s4ThLeftStyle: React.CSSProperties = {
      ...s4ThStyle,
      textAlign: "left"
    };

    const s4TdStyle: React.CSSProperties = {
      padding: "10px 12px",
      textAlign: "center",
      color: "var(--text-primary)"
    };

    const s4TdBoldStyle: React.CSSProperties = {
      padding: "12px 12px",
      textAlign: "center",
      color: "var(--text-primary)",
      fontWeight: 900
    };

    return (
      <div style={{ display: "grid", gap: 20 }}>
        <div style={{
          padding: "14px 18px",
          background: qaBg,
          border: `1px solid ${qaBorder}`,
          borderRadius: 12,
          display: "flex",
          flexDirection: "column",
          gap: 4
        }}>
          <span style={{ fontSize: 11, fontWeight: 900, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Dataset Quality Assessment</span>
          <span style={{ fontSize: 14, fontWeight: 800, color: qaColor }}>{qaText}</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            gap: 12
          }}>
            <div>
              <p style={{ fontSize: 11, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Plagiarism Risk Score</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>Weighted metric based on detection types</p>
            </div>
            <div style={{
              alignSelf: "flex-start",
              padding: "6px 14px",
              background: prsBg,
              border: `1px solid ${prsColor}20`,
              borderRadius: 20,
              fontSize: 16,
              fontWeight: 900,
              color: prsColor
            }}>
              {prs.toFixed(1)} / 100
            </div>
          </div>

          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            gap: 12
          }}>
            <div>
              <p style={{ fontSize: 11, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Combined Flag Rate</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>Unique flagged rows vs. total entries</p>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontSize: 24, fontWeight: 900, color: "var(--text-primary)" }}>{overallRate}</span>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>({overallUnique} / {totalRows} rows)</span>
            </div>
          </div>
        </div>

        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          overflow: "hidden"
        }}>
          <div style={{ padding: 14, borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
            <p style={{ fontSize: 13, fontWeight: 900, color: "var(--text-primary)" }}>Detection Methods Breakdown</p>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={s4ThLeftStyle}>Detection Method</th>
                  <th style={s4ThStyle}>Flagged Pairs</th>
                  <th style={s4ThStyle}>Unique Rows Flagged</th>
                  <th style={s4ThStyle}>Total Rows</th>
                  <th style={s4ThStyle}>Flag Rate</th>
                  <th style={s4ThStyle}>Risk Level</th>
                </tr>
              </thead>
              <tbody>
                {rowsData.map((row) => (
                  <tr key={row.method} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 12px", color: "var(--text-primary)", fontWeight: 800 }}>{row.method}</td>
                    <td style={s4TdStyle}>{row.pairs}</td>
                    <td style={s4TdStyle}>{row.unique}</td>
                    <td style={s4TdStyle}>{totalRows}</td>
                    <td style={s4TdStyle}>{row.rate}</td>
                    <td style={{ padding: "10px 12px", textAlign: "center" }}>
                      <span style={{
                        display: "inline-block",
                        padding: "3px 10px",
                        borderRadius: 12,
                        background: row.bg,
                        color: row.color,
                        fontSize: 12,
                        fontWeight: 800
                      }}>
                        {row.risk}
                      </span>
                    </td>
                  </tr>
                ))}
                <tr style={{ background: "var(--bg-secondary)", borderBottom: "none" }}>
                  <td style={{ padding: "12px 12px", color: "var(--text-primary)", fontWeight: 900 }}>All Methods Combined</td>
                  <td style={s4TdBoldStyle}>{overallPairs}</td>
                  <td style={s4TdBoldStyle}>{overallUnique}</td>
                  <td style={s4TdBoldStyle}>{totalRows}</td>
                  <td style={s4TdBoldStyle}>{overallRate}</td>
                  <td style={{ padding: "12px 12px", textAlign: "center" }}>
                    <span style={{
                      display: "inline-block",
                      padding: "3px 10px",
                      borderRadius: 12,
                      background: overallRiskBg,
                      color: overallRiskColor,
                      fontSize: 12,
                      fontWeight: 900
                    }}>
                      {overallRisk}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
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
