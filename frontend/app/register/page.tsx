"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function RegisterPage() {
  const [batchName, setBatchName] = useState("");
  const [texts, setTexts] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [buildEmbeddings, setBuildEmbeddings] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ batch_id: string; total_rows: number; embeddings_built: boolean; model?: string; batch_name: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    if (!file && !texts.trim()) {
      setError("Provide a file or some text to register.");
      setLoading(false);
      return;
    }

    const formData = new FormData();
    if (file) formData.append("file", file);
    const normalizedTexts = texts.replace(/\n+/g, ",");
    if (!file && normalizedTexts.trim()) formData.append("texts", normalizedTexts);
    if (batchName.trim()) formData.append("batch_name", batchName.trim());
    formData.append("build_embeddings", String(buildEmbeddings));

    try {
      const res = await fetch(`${API_BASE}/api/v1/ingest/reference/register`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Registration failed");
      setResult({
        batch_id: data.batch_id,
        total_rows: data.total_rows,
        embeddings_built: data.embeddings_built,
        model: data.model,
        batch_name: batchName.trim() || "Auto-generated",
      });
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--bg-primary)",
        padding: "120px 24px 80px",
      }}
    >
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <span
            style={{
              display: "inline-block",
              padding: "4px 14px",
              borderRadius: 99,
              background: "var(--accent-glow)",
              color: "var(--accent)",
              fontSize: 13,
              fontWeight: 600,
              marginBottom: 14,
              border: "1px solid var(--accent-glow)",
            }}
          >
            Reference Registration
          </span>
          <h1 style={{ fontSize: "clamp(28px,4vw,42px)", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-1px", lineHeight: 1.1 }}>
            Register a reference batch
          </h1>
          <p style={{ color: "var(--text-secondary)", maxWidth: 620, margin: "12px auto 0", lineHeight: 1.6 }}>
            Upload a CSV/Excel/TXT file or paste text to store as a reference batch. You will get a batch ID and the name you provide to use in cross-batch checks.
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: "24px", boxShadow: "var(--shadow-sm)" }}>
          <div style={{ marginBottom: 18 }}>
            <label style={{ display: "block", fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 8 }}>Batch name (optional)</label>
            <input
              type="text"
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
              placeholder="e.g. Marketing_Q1_refs"
              style={{ width: "100%", padding: "12px 14px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)" }}
            />
          </div>

          <div style={{ marginBottom: 18 }}>
            <label style={{ display: "block", fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 8 }}>Upload file (CSV, XLSX, XLS, TXT)</label>
            <div
              style={{
                border: "1.5px dashed var(--border)",
                borderRadius: 12,
                padding: "14px 16px",
                background: "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(139,92,246,0.05))",
              }}
            >
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.txt"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                style={{ display: "block", marginBottom: 10 }}
              />
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>Drop or pick a file. If you add a file, the textarea below is ignored.</p>
            </div>
          </div>

          <div style={{ marginBottom: 18 }}>
            <label style={{ display: "block", fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 8 }}>Or paste text (comma-separated)</label>
            <textarea
              value={texts}
              onChange={(e) => setTexts(e.target.value)}
              placeholder={"Line one text,\nLine two text,\nLine three text"}
              rows={4}
              style={{ width: "100%", padding: "12px 14px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)", resize: "vertical" }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
            <input
              id="build-embeddings"
              type="checkbox"
              checked={buildEmbeddings}
              onChange={(e) => setBuildEmbeddings(e.target.checked)}
            />
            <label htmlFor="build-embeddings" style={{ fontSize: 14, color: "var(--text-secondary)" }}>Build embeddings (recommended for semantic checks)</label>
          </div>

          {error && (
            <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 10, background: "#FEE2E2", border: "1px solid #FECACA", color: "#991B1B", fontSize: 14 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "12px 16px",
              borderRadius: 12,
              border: "none",
              background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
              color: "white",
              fontWeight: 700,
              fontSize: 15,
              cursor: loading ? "not-allowed" : "pointer",
              boxShadow: "0 10px 26px var(--accent-glow)",
              transition: "transform 0.2s",
            }}
          >
            {loading ? "Registering..." : "Register Batch"}
          </button>
        </form>

        {result && (
          <div style={{ marginTop: 22, padding: "16px 18px", borderRadius: 14, border: "1px solid var(--border)", background: "var(--bg-secondary)", boxShadow: "var(--shadow-sm)" }}>
            <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 8, color: "var(--text-primary)" }}>Batch registered</h2>
            <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}><strong>Batch ID:</strong> {result.batch_id}</p>
            <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}><strong>Name:</strong> {result.batch_name}</p>
            <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}><strong>Total rows:</strong> {result.total_rows}</p>
            <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 0 }}>
              <strong>Embeddings:</strong> {result.embeddings_built ? `Built (${result.model || "model"})` : "Not built"}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
