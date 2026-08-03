/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Aktiv Grotesk'", 'system-ui', 'sans-serif'],
        sans: ["'Aktiv Grotesk'", 'system-ui', 'sans-serif'],
        mono: ["'JetBrains Mono'", 'monospace'],
      },
      colors: {
        // Sovereign palette. Obsidian and Graphite carry the surfaces; Gold is
        // the single brand accent; Signal Blue and Insight Violet are the two
        // data accents. The V1 Indigo (#5B5FEE) / Neon Cyan (#00D4FF) pairing
        // is retired — `purple` and `cyan` are kept as aliases only so a
        // straggling class name renders in-palette rather than falling back to
        // an undefined colour.
        saibyl: {
          obsidian: '#0A0F1C',
          graphite: '#111827',
          'signal-blue': '#2563EB',
          'insight-violet': '#8B5CF6',

          void: '#0A0F1C',      // page background — Obsidian
          deep: '#0D1424',      // panel background, one step up from the page
          surface: '#111827',   // cards — Graphite
          elevated: '#1A2233',  // cards on cards
          gold: '#C9A227',
          'gold-hover': '#D4AF37',
          purple: '#8B5CF6',    // alias → Insight Violet
          cyan: '#2563EB',      // alias → Signal Blue
          blue: '#2563EB',
          violet: '#8B5CF6',
          platinum: '#E8ECF2',
          silver: '#8B97A8',
          muted: '#5A6578',
          positive: '#22C55E',
          negative: '#EF4444',
          warning: '#F59E0B',
          neutral: '#64748B',
          border: '#1E293B',
          'border-light': '#2A3A55',
          'border-active': 'rgba(139,92,246,0.5)',
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
