/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Accent colors - these use CSS variables so they adapt to theme
        // The values here are for utility classes like bg-accent-primary
        // Dark theme uses more vibrant colors, light theme uses softer ones
        accent: {
          // These are the DARK mode values (more vibrant)
          // Light mode should use emerald-*/red-*/amber-* instead
          primary: '#00FF9D',
          'primary-dim': '#00CC7D',
          danger: '#FF3366',
          'danger-dim': '#CC2952',
          warning: '#FFB800',
          'warning-dim': '#CC9300',
          info: '#00D4FF',
          'info-dim': '#00A9CC',
        },
        // Dark surface palette
        surface: {
          base: '#0A0E14',
          raised: '#111820',
          overlay: '#141B22',
          elevated: '#1C2530',
          border: '#2A3441',
          'border-strong': '#3D4A5C',
        },
      },
      fontFamily: {
        display: ['Rajdhani', 'system-ui', 'sans-serif'],
        mono: ['Share Tech Mono', 'Consolas', 'monospace'],
        sans: ['Exo 2', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'scan-line': 'scan-line 3s linear infinite',
        'fade-in-up': 'fade-in-up 0.4s ease-out',
        'slide-in-right': 'slide-in-right 0.3s ease-out',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'scan-line': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      boxShadow: {
        'glow-sm': '0 0 15px -3px rgba(0, 255, 157, 0.15)',
        'glow-md': '0 0 30px -5px rgba(0, 255, 157, 0.2)',
        'glow-lg': '0 0 60px -15px rgba(0, 255, 157, 0.25)',
        'glow-danger': '0 0 30px -5px rgba(255, 51, 102, 0.3)',
        'inner-glow': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.05)',
      },
    },
  },
  plugins: [],
}
