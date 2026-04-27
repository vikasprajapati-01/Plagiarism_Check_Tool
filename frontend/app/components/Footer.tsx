"use client";

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer
      style={{
        background: "var(--bg-secondary)",
        borderTop: "1px solid var(--border)",
        padding: "48px 24px 28px",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Top Row */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 32,
            justifyContent: "space-between",
            marginBottom: 36,
          }}
        >
          {/* Brand */}
          <div style={{ maxWidth: 320 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11.25C17.25 23.15 21 18.25 21 13V7l-9-5z" fill="white" opacity="0.9"/>
                  <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <span style={{ fontWeight: 700, fontSize: 18, color: "var(--text-primary)" }}>
                Plagia<span className="gradient-text">Check</span>
              </span>
            </div>
            <p style={{ fontSize: 14, color: "var(--text-muted)", lineHeight: 1.65 }}>
              Enterprise-grade text duplicate & plagiarism detection. Built under Samsung PRISM research programme.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <p style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Navigation
            </p>
            {[
              { label: "Home", href: "#home" },
              { label: "About", href: "#about" },
              { label: "Analyze", href: "/analyze" },
              { label: "Register", href: "/register" },
            ].map((link) => (
              <a
                key={link.href}
                href={link.href}
                style={{
                  display: "block",
                  fontSize: 14,
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                  marginBottom: 10,
                  transition: "color 0.15s",
                }}
                onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--accent)")}
                onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--text-secondary)")}
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Analyzer */}
          <div>
            <p style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Analyzer
            </p>
            <a
              href="/analyze"
              style={{
                display: "block",
                fontSize: 14,
                color: "var(--text-secondary)",
                textDecoration: "none",
                marginBottom: 10,
                transition: "color 0.15s",
              }}
              onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--accent)")}
              onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--text-secondary)")}
            >
              Upload & Run Scan
            </a>
            <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.55, maxWidth: 260 }}>
              Upload files or folders, toggle web scan / AI detection, preview results, and download reports.
            </p>
          </div>

          {/* Tech Stack */}
          <div>
            <p style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Tech Stack
            </p>
            {["FastAPI", "Python", "SBERT", "RoBERTa", "SHA-256", "Next.js"].map((tech) => (
              <span
                key={tech}
                style={{
                  display: "inline-block",
                  padding: "3px 10px",
                  borderRadius: 99,
                  fontSize: 12,
                  fontWeight: 600,
                  background: "var(--bg-accent)",
                  color: "var(--text-secondary)",
                  border: "1px solid var(--border)",
                  margin: "0 5px 6px 0",
                }}
              >
                {tech}
              </span>
            ))}
          </div>
        </div>

        {/* Divider */}
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 20 }}>
          <p style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center" }}>
            © {year} PlagiaCheck · Samsung PRISM Research Programme · All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
