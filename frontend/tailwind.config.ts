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
        ground: "var(--color-ground)",
        sidebar: "var(--color-sidebar)",
        surface: "var(--color-surface)",
        ink: "var(--color-ink)",
        inkSoft: "var(--color-ink-soft)",
        muted: "var(--color-muted)",
        line: "var(--color-line)",
        inputLine: "var(--color-input-line)",
        accent: "var(--color-accent)",
        accentHover: "var(--color-accent-hover)",
        accentSoft: "var(--color-accent-soft)",
        accentDash: "var(--color-accent-dash)",
        bubble: "var(--color-bubble)",
        track: "var(--color-track)",
        info: "var(--color-info)",
        infoBg: "var(--color-info-bg)",
        warn: "var(--color-warn)",
        success: "var(--color-success)",
        successBg: "var(--color-success-bg)",
        successLine: "var(--color-success-line)",
        danger: "var(--color-danger)",
        dangerBg: "var(--color-danger-bg)",
        dangerLine: "var(--color-danger-line)",
        code: "var(--color-code)",
        codeText: "var(--color-code-text)",
        codeLine: "var(--color-code-line)",
      },
      fontFamily: {
        sans: ["var(--font-plex-sans)", "Segoe UI", "sans-serif"],
        mono: ["var(--font-plex-mono)", "Consolas", "monospace"],
      },
      maxWidth: {
        conversation: "720px",
      },
    },
  },
  plugins: [],
};

export default config;
