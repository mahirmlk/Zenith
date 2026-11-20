/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#2A2529',
          50: '#F2F0F1',
          100: '#E3E0E1',
          200: '#C7C0C3',
          300: '#ABA0A6',
          400: '#92848D',
          500: '#7A6C75',
          600: '#655A62',
          700: '#51484F',
          800: '#3E373C',
          900: '#2A2529',
          950: '#181417',
        },
        zenith: {
          bg: '#F3F0E7',
          surface: '#EBE7DC',
          border: '#DFD9CD',
          body: '#4A433F',
          muted: '#9B928A',
          'muted-light': '#C5BDB5',
          primary: '#2A2529',
          secondary: '#2A2529',
          accent: '#F3F0E7',
          'accent-soft': '#DFD9CD',
          'accent-glow': 'rgba(42, 37, 41, 0.08)',
        },
      },
      fontFamily: {
        sans: ['var(--font-geist)'],
        serif: ['var(--font-instrument)'],
        mono: ['var(--font-geist-mono)'],
        jakarta: ['var(--font-plus-jakarta)'],
        space: ['var(--font-geist)'],
        outfit: ['var(--font-geist)'],
      },
      boxShadow: {
        'soft': '0 4px 20px -4px rgba(10, 22, 51, 0.08), 0 1px 3px -1px rgba(10, 22, 51, 0.04)',
        'soft-lg': '0 12px 40px -8px rgba(10, 22, 51, 0.10), 0 4px 12px -4px rgba(10, 22, 51, 0.06)',
        'card': '0 2px 12px -2px rgba(10, 22, 51, 0.06), 0 1px 2px -1px rgba(10, 22, 51, 0.02)',
        'card-hover': '0 4px 24px -4px rgba(10, 22, 51, 0.10), 0 2px 6px -2px rgba(10, 22, 51, 0.04)',
        'glow': '0 0 40px -12px rgba(106, 174, 255, 0.25)',
        'button': '0 4px 16px -4px rgba(10, 22, 51, 0.20)',
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      transitionDuration: {
        '150': '150ms',
        '200': '200ms',
        '250': '250ms',
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'float-delayed': 'float 6s ease-in-out 2s infinite',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.25s ease-out forwards',
        'slide-up': 'slideUp 0.25s ease-out forwards',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
