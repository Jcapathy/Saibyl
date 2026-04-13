/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['Inter', 'system-ui'],
        sans: ['Inter', 'system-ui'],
        mono: ["'JetBrains Mono'", 'monospace'],
      },
      colors: {
        saibyl: {
          void: '#0A0F1C',
          deep: '#0F172A',
          surface: '#111827',
          elevated: '#1E293B',
          gold: '#C9A227',
          blue: '#2563EB',
          violet: '#8B5CF6',
          platinum: '#F1F5F9',
          silver: '#94A3B8',
          muted: '#64748B',
          positive: '#10B981',
          negative: '#EF4444',
          neutral: '#64748B',
          border: 'rgba(255,255,255,0.06)',
          'border-active': 'rgba(197,162,39,0.35)',
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
