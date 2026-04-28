"use client";

export default function HeroSection() {
  return (
    <section
      id="home"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        overflow: "hidden",
        paddingTop: 68,
      }}
    >
      {/* Animated Background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse 80% 60% at 50% 0%, var(--accent-glow) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "80px 24px",
          textAlign: "center",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* Badge */}
        <div
          className="animate-fade-up"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 16px",
            borderRadius: 99,
            border: "1px solid var(--border)",
            background: "var(--bg-card)",
            fontSize: 13,
            fontWeight: 500,
            color: "var(--accent)",
            marginBottom: 32,
            boxShadow: "var(--shadow-sm)",
            animationDelay: "0.1s",
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--accent)",
              display: "inline-block",
              animation: "pulse-glow 2s infinite",
            }}
          />
          Samsung PRISM — Research & Innovation Programme
        </div>

        {/* Headline */}
        <h1
          className="animate-fade-up"
          style={{
            fontSize: "clamp(38px, 6vw, 72px)",
            fontWeight: 900,
            lineHeight: 1.08,
            letterSpacing: "-2px",
            color: "var(--text-primary)",
            marginBottom: 24,
            animationDelay: "0.2s",
          }}
        >
          Text Duplicate &<br />
          <span className="gradient-text">Plagiarism Detection</span>
        </h1>

        {/* Sub-headline */}
        <p
          className="animate-fade-up"
          style={{
            fontSize: "clamp(16px, 2vw, 20px)",
            color: "var(--text-secondary)",
            maxWidth: 640,
            margin: "0 auto 40px",
            lineHeight: 1.7,
            animationDelay: "0.3s",
          }}
        >
          Multi-method AI-powered detection for exact duplicates, fuzzy matches,
          semantic similarity, AI-generated content, web plagiarism, and license
          violations — built for enterprise data quality.
        </p>

        {/* CTA Buttons */}
        <div
          className="animate-fade-up"
          style={{
            display: "flex",
            gap: 14,
            justifyContent: "center",
            flexWrap: "wrap",
            animationDelay: "0.4s",
          }}
        >
          <a
            href="/analyze"
            style={{
              padding: "14px 32px",
              borderRadius: 12,
              background: "linear-gradient(135deg, var(--accent), var(--accent-2))",
              color: "white",
              fontWeight: 700,
              fontSize: 16,
              textDecoration: "none",
              boxShadow: "0 8px 24px var(--accent-glow)",
              transition: "all 0.2s",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)"; (e.currentTarget as HTMLElement).style.boxShadow = "0 12px 32px var(--accent-glow)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.transform = "translateY(0)"; (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 24px var(--accent-glow)"; }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            Start Analyzing
          </a>
          <a
            href="#about"
            style={{
              padding: "14px 32px",
              borderRadius: 12,
              border: "1px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text-primary)",
              fontWeight: 600,
              fontSize: 16,
              textDecoration: "none",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)"; (e.currentTarget as HTMLElement).style.color = "var(--accent)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLElement).style.color = "var(--text-primary)"; }}
          >
            Learn More
          </a>
        </div>

        {/* Stats Row */}
        <div
          className="animate-fade-up"
          style={{
            display: "flex",
            justifyContent: "center",
            flexWrap: "wrap",
            gap: 16,
            marginTop: 64,
            animationDelay: "0.55s",
          }}
        >
          {[
            { value: "7", label: "Detection Methods", icon: "🔍" },
            { value: "SHA-256", label: "Hash Fingerprinting", icon: "🔐" },
            { value: "BERT", label: "Semantic AI Engine", icon: "🧠" },
            { value: "Excel/CSV", label: "Report Export", icon: "📊" },
          ].map((stat, idx) => (
            <div
              key={stat.label}
              className="glass animate-float"
              style={{
                padding: "16px 24px",
                borderRadius: 14,
                display: "flex",
                alignItems: "center",
                gap: 12,
                minWidth: 180,
                animationDelay: `${0.6 + idx * 0.18}s`,
              }}
            >
              <span style={{ fontSize: 26 }}>{stat.icon}</span>
              <div style={{ textAlign: "left" }}>
                <div style={{ fontWeight: 800, fontSize: 18, color: "var(--text-primary)" }}>{stat.value}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>{stat.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
