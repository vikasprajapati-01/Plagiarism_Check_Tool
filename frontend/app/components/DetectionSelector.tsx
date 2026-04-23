"use client";

import { useRouter } from "next/navigation";

const DETECTION_MODES = [
  {
    id: "exact",
    icon: "🔗",
    title: "Exact Duplicate",
    subtitle: "SHA-256 / MD5 hash matching",
    description:
      "Detects byte-perfect duplicates using cryptographic hash comparison. Instant and zero false-positives.",
    tags: ["SHA-256", "MD5", "Hash"],
    color: "#6366F1",
    route: "/analyze/exact",
  },
  {
    id: "fuzzy",
    icon: "〰️",
    title: "Fuzzy / Near Duplicate",
    subtitle: "Levenshtein · Jaccard · N-gram",
    description:
      "Catches near-duplicates with minor edits, typos, or rewordings using string similarity algorithms.",
    tags: ["Levenshtein", "Hamming", "Jaccard", "N-gram"],
    color: "#8B5CF6",
    route: "/analyze/fuzzy",
  },
  {
    id: "semantic",
    icon: "🧠",
    title: "Semantic Similarity",
    subtitle: "SBERT · BERT · Cosine similarity",
    description:
      "Understands meaning, not just words. Detects paraphrased and contextually similar content using transformers.",
    tags: ["BERT", "SBERT", "Embeddings"],
    color: "#06B6D4",
    route: "/analyze/semantic",
  },
  {
    id: "ai-detect",
    icon: "🤖",
    title: "AI Content Detection",
    subtitle: "RoBERTa-based classifier",
    description:
      "Identifies AI-generated text (ChatGPT, Bard, Claude etc.) using pre-trained transformer classifiers.",
    tags: ["RoBERTa", "Transformer", "Classifier"],
    color: "#F59E0B",
    route: "/analyze/ai-detect",
  },
  {
    id: "web-scan",
    icon: "🌐",
    title: "Web Plagiarism Scan",
    subtitle: "DuckDuckGo · Web Fingerprinting",
    description:
      "Searches the live web for matching content and computes similarity against found pages.",
    tags: ["DuckDuckGo", "Web", "Fingerprint"],
    color: "#10B981",
    route: "/analyze/web-scan",
  },
  {
    id: "cross-batch",
    icon: "🗄️",
    title: "Cross-Batch Detection",
    subtitle: "Exact · Fuzzy · Semantic across all batches",
    description:
      "Checks submitted texts against every reference batch stored in the database using your chosen method.",
    tags: ["Multi-batch", "Reference DB"],
    color: "#EC4899",
    route: "/analyze/cross-batch",
  },
  {
    id: "license",
    icon: "⚖️",
    title: "License / Copyright Check",
    subtitle: "OSS license fingerprinting",
    description:
      "Detects open-source license signatures (MIT, GPL, Apache, etc.) embedded in text or code snippets.",
    tags: ["MIT", "GPL", "Apache", "SPDX"],
    color: "#EF4444",
    route: "/analyze/license",
  },
  {
    id: "folder",
    icon: "📁",
    title: "Full Folder / Archive Scan",
    subtitle: "Unified Pipeline Detection",
    description:
      "Upload entire folders or .zip archives to automatically extract valid files and run all detection methods out of the box.",
    tags: ["Folder", "ZIP", "Pipeline"],
    color: "#14B8A6",
    route: "/analyze/folder",
  },
];

export default function DetectionSelector() {
  const router = useRouter();

  return (
    <section
      id="analyzer"
      style={{
        padding: "100px 24px",
        background: "var(--bg-primary)",
        borderTop: "1px solid var(--border)",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <span
            style={{
              display: "inline-block",
              padding: "4px 14px",
              borderRadius: 99,
              background: "var(--accent-glow)",
              color: "var(--accent)",
              fontSize: 13,
              fontWeight: 600,
              marginBottom: 16,
              border: "1px solid var(--accent-glow)",
            }}
          >
            Choose Detection Mode
          </span>
          <h2
            style={{
              fontSize: "clamp(26px,4vw,42px)",
              fontWeight: 800,
              color: "var(--text-primary)",
              letterSpacing: "-1px",
              lineHeight: 1.15,
            }}
          >
            What would you like to{" "}
            <span className="gradient-text">detect?</span>
          </h2>
          <p
            style={{
              marginTop: 14,
              color: "var(--text-secondary)",
              maxWidth: 560,
              margin: "14px auto 0",
              fontSize: 16,
            }}
          >
            Select a detection method below. Each opens a dedicated analyzer
            form pre-wired to the backend API.
          </p>
        </div>

        {/* Cards Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 18,
          }}
        >
          {DETECTION_MODES.map((mode) => (
            <button
              key={mode.id}
              onClick={() => router.push(mode.route)}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: 18,
                padding: "26px 24px",
                cursor: "pointer",
                textAlign: "left",
                transition: "all 0.22s cubic-bezier(0.4,0,0.2,1)",
                outline: "none",
                width: "100%",
                position: "relative",
                overflow: "hidden",
              }}
              onMouseEnter={(e) => {
                const el = e.currentTarget as HTMLElement;
                el.style.transform = "translateY(-4px)";
                el.style.boxShadow = `0 16px 40px ${mode.color}22`;
                el.style.borderColor = `${mode.color}55`;
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLElement;
                el.style.transform = "translateY(0)";
                el.style.boxShadow = "none";
                el.style.borderColor = "var(--border)";
              }}
            >
              {/* Color top bar */}
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 3,
                  background: mode.color,
                  borderRadius: "18px 18px 0 0",
                  opacity: 0.7,
                }}
              />

              {/* Icon & Arrow Row */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  marginBottom: 14,
                  marginTop: 8,
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: `${mode.color}18`,
                    border: `1px solid ${mode.color}30`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 22,
                  }}
                >
                  {mode.icon}
                </div>
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke={mode.color}
                  strokeWidth="2.5"
                  style={{ opacity: 0.7 }}
                >
                  <path d="M7 17L17 7M17 7H7M17 7v10" />
                </svg>
              </div>

              {/* Text */}
              <h3
                style={{
                  fontWeight: 700,
                  fontSize: 17,
                  color: "var(--text-primary)",
                  marginBottom: 4,
                  lineHeight: 1.3,
                }}
              >
                {mode.title}
              </h3>
              <p
                style={{
                  fontSize: 12,
                  color: mode.color,
                  fontWeight: 600,
                  marginBottom: 10,
                  opacity: 0.9,
                }}
              >
                {mode.subtitle}
              </p>
              <p
                style={{
                  fontSize: 14,
                  color: "var(--text-secondary)",
                  lineHeight: 1.55,
                  marginBottom: 16,
                }}
              >
                {mode.description}
              </p>

              {/* Tags */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {mode.tags.map((tag) => (
                  <span
                    key={tag}
                    style={{
                      padding: "3px 10px",
                      borderRadius: 99,
                      fontSize: 11,
                      fontWeight: 600,
                      background: `${mode.color}14`,
                      color: mode.color,
                      border: `1px solid ${mode.color}25`,
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
