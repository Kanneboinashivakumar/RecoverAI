/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Design System tokens from 02-DESIGN-SYSTEM.md
        background: '#F7F8FA',
        surface: '#FFFFFF',
        border: '#E4E7EC',
        'text-primary': '#101828',
        'text-secondary': '#667085',
        accent: '#3538CD',
        success: '#12B76A',
        warning: '#F79009',
        danger: '#F04438',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      fontSize: {
        'kpi': ['2rem', { lineHeight: '2.5rem', fontWeight: '700' }],
        'section': ['1rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'body': ['0.875rem', { lineHeight: '1.25rem', fontWeight: '400' }],
        'caption': ['0.75rem', { lineHeight: '1rem', fontWeight: '400' }],
      },
    },
  },
  plugins: [],
}
