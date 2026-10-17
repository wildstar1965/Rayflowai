/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#FFFFFF',
        surface: {
          DEFAULT: '#FFFFFF',
          subtle: '#FAFAFA',
          muted: '#F4F4F5',
          hover: '#F4F4F5',
          border: '#E4E4E7',
          dark: '#18181B',
        },
        charcoal: {
          DEFAULT: '#18181B',
          muted: '#71717A',
          faint: '#A1A1AA',
          border: '#E4E4E7',
        },
        accent: {
          DEFAULT: '#18181B',
          hover: '#27272A',
          subtle: '#2563EB',
        },
        border: {
          DEFAULT: '#E4E4E7',
          subtle: '#F4F4F5',
          dark: '#27272A',
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
