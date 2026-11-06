/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0e11',
          800: '#15191e',
          700: '#1e2329',
          600: '#2b313a',
        },
        trade: {
          green: '#0ecb81',
          red: '#f6465d',
        }
      }
    },
  },
  plugins: [],
}
