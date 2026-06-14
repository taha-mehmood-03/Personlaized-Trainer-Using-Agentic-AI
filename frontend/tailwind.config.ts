import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/hooks/**/*.{js,ts,jsx,tsx}',
    './src/lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'cyan-brand': '#0891b2',
        'emerald-brand': '#059669',
        'ink-brand': '#0f172a',
        'purple-brand': '#0891b2',
        'teal-brand': '#059669',
        'slate-dark': '#1e293b',
      },
      fontFamily: {
        sans: ['var(--font-geist-sans)', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['var(--font-geist-mono)', 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'monospace'],
      },
      animation: {
        'pulse-slow':      'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'bounce-gentle':   'bounce 2s infinite',
        'fade-in':         'fadeIn 0.5s ease-in',
        'slide-up':        'slideUp 0.4s ease-out',
        'slide-down':      'slideDown 0.4s ease-out',
        'scale-in':        'scaleIn 0.3s ease-out',
        'shimmer':         'shimmer 2s infinite',
        'recording-pulse': 'recordingPulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',     opacity: '1' },
        },
        slideDown: {
          '0%':   { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',      opacity: '1' },
        },
        scaleIn: {
          '0%':   { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)',    opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0'  },
        },
        recordingPulse: {
          '0%, 100%': { transform: 'scale(1)',   opacity: '1' },
          '50%':      { transform: 'scale(1.1)', opacity: '0.8' },
        },
      },
      boxShadow: {
        'soft':   '0 4px 6px rgba(0, 0, 0, 0.05)',
        'medium': '0 10px 15px rgba(0, 0, 0, 0.1)',
        'glow':   '0 0 20px rgba(8, 145, 178, 0.35)',
      },
      backdropBlur: {
        'xs': '2px',
      },
    },
  },
  plugins: [],
}

export default config
