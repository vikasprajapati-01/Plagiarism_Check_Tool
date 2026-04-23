"use client";

import Link from "next/link";
import { useTheme } from "../components/ThemeProvider";

interface Props {
  title: string;
  subtitle: string;
  icon: string;
  color: string;
  children: React.ReactNode;
}

export default function AnalyzerLayout({ title, subtitle, icon, color, children }: Props) {
  const { theme, toggleTheme } = useTheme();

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", flexDirection: "column" }}>
      {/* Top Nav */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 100,
          background: theme === "dark" ? "rgba(18,18,18,0.92)" : "rgba(255,255,255,0.92)",
          backdropFilter: "blur(20px)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            maxWidth: 900,
            margin: "0 auto",
            padding: "0 24px",
            height: 60,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Link
            href="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              textDecoration: "none",
              color: "var(--text-secondary)",
              fontSize: 14,
              fontWeight: 500,
              transition: "color 0.15s",
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--accent)")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--text-secondary)")}
          >
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back to Home
          </Link>

          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
            <div
              style={{
                width: 28, height: 28, borderRadius: 8,
                background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11.25C17.25 23.15 21 18.25 21 13V7l-9-5z" fill="white" opacity="0.9"/>
                <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>
              Plagia<span className="gradient-text">Check</span>
            </span>
          </Link>

          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            style={{
              width: 36, height: 36, borderRadius: 8, border: "1px solid var(--border)",
              background: "var(--bg-accent)", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--text-secondary)",
            }}
          >
            {theme === "dark" ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            ) : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
              </svg>
            )}
          </button>
        </div>
      </header>

      {/* Page Header */}
      <div
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
          padding: "40px 24px",
        }}
      >
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div
              style={{
                width: 56, height: 56, borderRadius: 14,
                background: `${color}18`, border: `1px solid ${color}35`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26,
              }}
            >
              {icon}
            </div>
            <div>
              <h1 style={{ fontSize: "clamp(20px,3vw,30px)", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.5px" }}>
                {title}
              </h1>
              <p style={{ fontSize: 14, color: "var(--text-muted)", marginTop: 2 }}>{subtitle}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main style={{ flex: 1, padding: "40px 24px", maxWidth: 900, margin: "0 auto", width: "100%" }}>
        {children}
      </main>
    </div>
  );
}
