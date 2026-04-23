"use client";

function BulletItem({ children }: { children: React.ReactNode }) {
  return (
    <li
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        marginBottom: 10,
        fontSize: 15,
        color: "var(--text-secondary)",
        lineHeight: 1.6,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "var(--accent)",
          marginTop: 8,
          flexShrink: 0,
        }}
      />
      {children}
    </li>
  );
}

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 16,
        padding: "28px 28px",
        height: "100%",
        boxShadow: "var(--shadow-sm)",
        transition: "box-shadow 0.2s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-sm)";
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <span style={{ fontSize: 22 }}>{icon}</span>
        <h3 style={{ fontWeight: 700, fontSize: 18, color: "var(--text-primary)" }}>
          {title}
        </h3>
      </div>
      <ul style={{ listStyle: "none", padding: 0 }}>{children}</ul>
    </div>
  );
}

export default function AboutSection() {
  return (
    <section
      id="about"
      style={{
        padding: "100px 24px",
        background: "var(--bg-secondary)",
        borderTop: "1px solid var(--border)",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Section Header */}
        <div style={{ textAlign: "center", marginBottom: 60 }}>
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
            About the Website
          </span>
          <h2
            style={{
              fontSize: "clamp(28px,4vw,44px)",
              fontWeight: 800,
              color: "var(--text-primary)",
              letterSpacing: "-1px",
              lineHeight: 1.15,
            }}
          >
            Plagiarism and Duplicate Checks in One Place
          </h2>
          <p
            style={{
              marginTop: 14,
              color: "var(--text-secondary)",
              maxWidth: 620,
              margin: "14px auto 0",
              fontSize: 16,
            }}
          >
            Upload short text batches, run exact, fuzzy, semantic, AI, license, and web-scan
            methods together, then export clean reports in CSV or Excel for review and follow-up.
          </p>
        </div>

        {/* Cards Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: 20,
          }}
        >
          <Card title="Detection Coverage" icon="🧭">
            <BulletItem>Exact match checks to flag identical text quickly.</BulletItem>
            <BulletItem>Fuzzy and near-duplicate search with adjustable similarity thresholds.</BulletItem>
            <BulletItem>Semantic analysis for paraphrases and contextually similar lines.</BulletItem>
            <BulletItem>AI-generated content cues and web-source fingerprinting.</BulletItem>
          </Card>

          <Card title="How you use it" icon="🛠️">
            <BulletItem>Upload CSV or Excel text batches; short snippets (&lt;20 words) are optimized.</BulletItem>
            <BulletItem>Paste a single sentence or short text directly—no file required.</BulletItem>
            <BulletItem>Run exact, fuzzy, semantic, AI-detect, license, and web-scan flows in one place.</BulletItem>
            <BulletItem>Tune thresholds and pick methods per analysis run.</BulletItem>
          </Card>

          <Card title="Outputs & reporting" icon="📑">
            <BulletItem>Download results as CSV or Excel with per-entry flags and scores.</BulletItem>
            <BulletItem>See which method caught each hit and why (hash, similarity, semantic, AI/web signals).</BulletItem>
            <BulletItem>License and web-scan notes help filter risky content before reuse.</BulletItem>
          </Card>
        </div>

        {/* Project Info Banner */}
        <div
          className="glass"
          style={{
            marginTop: 32,
            borderRadius: 16,
            padding: "24px 32px",
            display: "flex",
            flexWrap: "wrap",
            gap: 24,
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {[
            { icon: "🗂️", label: "Input", value: "CSV / Excel" },
            { icon: "⚙️", label: "Methods", value: "Exact · Fuzzy · Semantic · AI · Web" },
            { icon: "📤", label: "Exports", value: "Excel / CSV" },
            { icon: "🌐", label: "Web Scan", value: "Live source lookup" },
            { icon: "🛡️", label: "License", value: "Basic license cues" },
          ].map((item) => (
            <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 22 }}>{item.icon}</span>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  {item.label}
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                  {item.value}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
