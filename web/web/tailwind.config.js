/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#03070d',
        panel: '#07101a',
        panel2: '#091522',
        cyan: '#16d9ff',
        green: '#20e6a0',
        purple: '#b47cff',
        orange: '#ffb45c',
        red: '#ff637d',
        text: '#d8e7f2',
        muted: '#6f8799',
      }
    }
  }
}