/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#08090D',
        surface: {
          DEFAULT: '#11131A',
          elevated: '#181B24',
          hover: '#1F232E',
          active: '#262A36'
        },
        accent: {
          blue: '#3B82F6',
          violet: '#8B5CF6',
          cyan: '#67E8F9',
        },
        text: {
          primary: '#F5F7FB',
          secondary: '#9299AA',
          muted: '#626875'
        },
        border: {
          subtle: 'rgba(255, 255, 255, 0.07)',
          medium: 'rgba(255, 255, 255, 0.12)',
          accent: 'rgba(59, 130, 246, 0.3)',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        cinematic: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
