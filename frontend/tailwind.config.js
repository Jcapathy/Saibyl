/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['Manrope', 'system-ui', 'sans-serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        serif: ["'Playfair Display'", 'Georgia', 'serif'],
        mono: ["'DM Mono'", 'ui-monospace', 'monospace'],
      },
      colors: {
        // The Saido light palette — the app-wide port of the landing page's
        // system (frontend/src/pages/landing.css). Paper carries the ground,
        // ink carries the text, hairlines carry the density, and Blue is the
        // one accent that means "action". Green/amber/rose are semantic status
        // colours, deliberately distinct from the accent. The dark-era token
        // NAMES are kept so token-riding components flip wholesale: `void`
        // now means the paper ground, `gold` now means the blue accent, and
        // `platinum` means ink. Every text-bearing value here holds ≥4.5:1 on
        // white and on paper.
        saibyl: {
          paper: '#f8fbff',
          ink: '#14294a',
          line: '#264f8b24',
          'signal-blue': '#286cf0',
          'insight-violet': '#8b73ee',

          void: '#f8fbff',      // page background — paper
          deep: '#eef4fc',      // panel background, one step below the page
          surface: '#ffffff',   // cards
          elevated: '#f3f7fd',  // cards on cards
          gold: '#286cf0',      // legacy accent name → the blue accent
          'gold-hover': '#1e5ad9',
          purple: '#8b73ee',    // alias → Insight Violet
          cyan: '#35c7d5',
          blue: '#286cf0',
          /* The hover pair for `blue`, and it did not exist until 2026-08-23.
             `gold-hover` did — so the app-wide sweep off the legacy aliases
             (`gold` → `blue`) would have turned every `saibyl-gold-hover` into
             a `saibyl-blue-hover` that Tailwind resolves to nothing, silently
             dropping the hover state on every button that had one. Same value
             `gold-hover` always held. */
          'blue-hover': '#1e5ad9',
          violet: '#8b73ee',
          platinum: '#14294a',  // primary text — ink
          white: '#14294a',     // legacy "white text" → ink on the light ground
          silver: '#44587a',    // secondary text
          muted: '#60718e',     // muted text — 4.7:1 on paper
          positive: '#0e7d55',
          negative: '#d92d3c',
          warning: '#b45309',
          neutral: '#60718e',
          green: '#2fbf8a',     // fills and dots only — not text-safe
          rose: '#ff6e79',      // fills and dots only — not text-safe
          border: '#264f8b24',
          'border-light': '#264f8b3d',
          'border-active': 'rgba(40,108,240,0.45)',
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
