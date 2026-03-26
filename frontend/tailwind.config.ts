import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        panel: "var(--color-panel)",
        panelStrong: "var(--color-panel-strong)",
        ink: "var(--color-ink)",
        muted: "var(--color-muted)",
        line: "var(--color-line)",
        accent: "var(--color-accent)",
        accentSoft: "var(--color-accent-soft)",
        success: "var(--color-success)",
        info: "var(--color-info)",
      },
      boxShadow: {
        soft: "0 18px 40px rgba(48, 29, 13, 0.10)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        mono: ["var(--font-mono)"],
      },
      backgroundImage: {
        "hero-wash":
          "radial-gradient(circle at top left, rgba(247, 173, 103, 0.20), transparent 28%), radial-gradient(circle at 82% 12%, rgba(34, 102, 156, 0.16), transparent 20%), linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0.52))",
      },
    },
  },
  plugins: [],
};

export default config;
