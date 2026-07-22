import type { Config } from "tailwindcss"

const withOpacity =
  (variable: string) =>
  ({ opacityValue }: { opacityValue?: string }) =>
    opacityValue !== undefined
      ? `rgb(var(${variable}) / ${opacityValue})`
      : `rgb(var(${variable}))`

const config: Config = {
  darkMode: "class",
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: withOpacity("--color-background"),
        surface: withOpacity("--color-surface"),
        "surface-elevated": withOpacity("--color-surface-elevated"),
        primary: withOpacity("--color-primary"),
        "primary-hover": withOpacity("--color-primary-hover"),
        accent: withOpacity("--color-accent"),
        gold: withOpacity("--color-gold"),
        ink: withOpacity("--color-text-primary"),
        "ink-muted": withOpacity("--color-text-secondary"),
        success: withOpacity("--color-success"),
        warning: withOpacity("--color-warning"),
        danger: withOpacity("--color-danger-text"),
        "danger-border": withOpacity("--color-danger-border"),
        hairline: "var(--color-border)",
        "danger-bg": "var(--color-danger-bg)",
      },
      boxShadow: {
        premium: "0 8px 24px -8px var(--color-shadow)",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
      },
      borderColor: {
        DEFAULT: "var(--color-border)",
      },
    },
  },
  plugins: [],
}

export default config
