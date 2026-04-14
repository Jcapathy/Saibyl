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
        saibyl: {
          void: '#070B14',
          deep: '#0D1117',
          surface: '#111820',
          elevated: '#161E28',
          gold: '#C9A227',
          'gold-hover': '#D4AF37',
          purple: '#5B5FEE',
          cyan: '#00D4FF',
          blue: '#3B82F6',
          violet: '#818CF8',
          platinum: '#E8ECF2',
          silver: '#8B97A8',
          muted: '#5A6578',
          positive: '#22C55E',
          negative: '#EF4444',
          warning: '#F59E0B',
          neutral: '#64748B',
          border: '#1B2433',
          'border-light': '#243044',
          'border-active': 'rgba(91,95,238,0.5)',
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
