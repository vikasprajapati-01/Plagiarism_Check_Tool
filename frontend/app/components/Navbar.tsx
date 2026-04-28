"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useTheme } from "./ThemeProvider";

const NAV_LINKS = [
  { label: "Home",      href: "#home" },
  { label: "About",     href: "#about" },
  { label: "Analyze",   href: "/analyze" },
  { label: "Register",  href: "/register" },
];

export default function Navbar() {
  const { theme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        transition: "all 0.3s ease",
        background: scrolled
          ? theme === "dark"
            ? "rgba(18,18,18,0.88)"
            : "rgba(255,255,255,0.88)"
          : "transparent",
        backdropFilter: scrolled ? "blur(20px) saturate(180%)" : "none",
        borderBottom: scrolled ? "1px solid var(--border)" : "none",
      }}
    >
      <nav
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "0 24px",
          height: 68,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        {/* Logo */}
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 4px 12px var(--accent-glow)",
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11.25C17.25 23.15 21 18.25 21 13V7l-9-5z" fill="white" opacity="0.9"/>
              <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span style={{ fontWeight: 700, fontSize: 20, color: "var(--text-primary)", letterSpacing: "-0.5px" }}>
            Plagia<span className="gradient-text">Check</span>
          </span>
        </Link>

        {/* Desktop Nav */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }} className="desktop-nav">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              style={{
                padding: "8px 16px",
                borderRadius: 8,
                textDecoration: "none",
                color: "var(--text-secondary)",
                fontWeight: 500,
                fontSize: 15,
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLElement).style.color = "var(--accent)";
                (e.target as HTMLElement).style.background = "var(--bg-accent)";
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLElement).style.color = "var(--text-secondary)";
                (e.target as HTMLElement).style.background = "transparent";
              }}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--bg-accent)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-secondary)",
              transition: "all 0.2s",
            }}
          >
            {theme === "dark" ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
              </svg>
            )}
          </button>

          {/* CTA */}
          <Link
            href="/analyze"
            style={{
              padding: "9px 20px",
              borderRadius: 10,
              background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
              color: "white",
              fontWeight: 600,
              fontSize: 14,
              textDecoration: "none",
              boxShadow: "0 4px 12px var(--accent-glow)",
              transition: "all 0.2s",
              whiteSpace: "nowrap",
            }}
          >
            Try Now
          </Link>

          {/* Mobile Hamburger */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="mobile-only"
            aria-label="Toggle menu"
            style={{
              width: 40,
              height: 40,
              border: "1px solid var(--border)",
              borderRadius: 10,
              background: "var(--bg-accent)",
              cursor: "pointer",
              display: "none",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
            }}
          >
            <span style={{ width: 18, height: 2, background: "var(--text-primary)", borderRadius: 2, display: "block" }} />
            <span style={{ width: 18, height: 2, background: "var(--text-primary)", borderRadius: 2, display: "block" }} />
            <span style={{ width: 18, height: 2, background: "var(--text-primary)", borderRadius: 2, display: "block" }} />
          </button>
        </div>
      </nav>

      {/* Mobile Menu */}
      {menuOpen && (
        <div
          style={{
            background: "var(--bg-secondary)",
            borderTop: "1px solid var(--border)",
            padding: "12px 24px 20px",
          }}
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              style={{
                display: "block",
                padding: "12px 0",
                color: "var(--text-secondary)",
                textDecoration: "none",
                fontWeight: 500,
                borderBottom: "1px solid var(--border)",
              }}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}

      <style>{`
        @media (max-width: 768px) {
          .desktop-nav { display: none !important; }
          .mobile-only  { display: flex !important; }
        }
      `}</style>
    </header>
  );
}
