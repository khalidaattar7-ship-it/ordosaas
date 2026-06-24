/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // Design tokens extracted from the OrdoSaaS .dc.html mockups
      colors: {
        // Dark chrome (sidebar / hero)
        sidebar: '#0C0D18',
        ink: '#0C0D18',
        'ink-soft': '#18191F',
        // Brass / gold brand accent
        accent: '#C4963A',
        'accent-dark': '#A87E2E',
        gold: '#C4963A',
        // Warm cream surfaces
        cream: '#F4F3F0',
        'cream-card': '#FDFCFB',
        // Status
        success: '#2A7A5B',
        danger: '#C84848',
        muted: '#8A8A9E',
        'brand-border': '#DDDBD6',
      },
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
