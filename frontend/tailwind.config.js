/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // Script-parser character classes are not Tailwind arbitrary CSS properties.
  blocklist: ['[-:–—]'],
  theme: {
    extend: {
      colors: {
        studio: Object.fromEntries(['canvas', 'panel', 'raised', 'hover', 'border', 'line', 'text', 'muted', 'quiet'].map(
          name => [name, `rgb(var(--rayflow-${name}) / <alpha-value>)`],
        )),
        ink: 'rgb(var(--rayflow-canvas) / <alpha-value>)',
        brass: {
          DEFAULT: 'rgb(var(--rayflow-brass) / <alpha-value>)',
          soft: 'rgb(var(--rayflow-brass-soft) / <alpha-value>)',
          border: 'rgb(var(--rayflow-brass-border) / <alpha-value>)',
        },
        jade: {
          DEFAULT: 'rgb(var(--rayflow-jade) / <alpha-value>)',
          soft: 'rgb(var(--rayflow-jade-soft) / <alpha-value>)',
          border: 'rgb(var(--rayflow-jade-border) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--rayflow-danger) / <alpha-value>)',
          soft: 'rgb(var(--rayflow-danger-soft) / <alpha-value>)',
          border: 'rgb(var(--rayflow-danger-border) / <alpha-value>)',
        },
        background: 'rgb(var(--rayflow-canvas) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--rayflow-panel) / <alpha-value>)',
          subtle: 'rgb(var(--rayflow-raised) / <alpha-value>)',
          muted: 'rgb(var(--rayflow-hover) / <alpha-value>)',
          hover: 'rgb(var(--rayflow-hover) / <alpha-value>)',
          border: 'rgb(var(--rayflow-border) / <alpha-value>)',
          dark: 'rgb(var(--rayflow-canvas) / <alpha-value>)',
        },
        charcoal: {
          DEFAULT: 'rgb(var(--rayflow-text) / <alpha-value>)',
          muted: 'rgb(var(--rayflow-muted) / <alpha-value>)',
          faint: 'rgb(var(--rayflow-quiet) / <alpha-value>)',
          border: 'rgb(var(--rayflow-border) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--rayflow-vermilion) / <alpha-value>)',
          hover: 'rgb(var(--rayflow-vermilion-hover) / <alpha-value>)',
          subtle: 'rgb(var(--rayflow-jade) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--rayflow-border) / <alpha-value>)',
          subtle: 'rgb(var(--rayflow-line) / <alpha-value>)',
          dark: 'rgb(var(--rayflow-line) / <alpha-value>)',
        }
      },
      borderColor: {
        DEFAULT: 'rgb(var(--rayflow-border) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['Onest', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
