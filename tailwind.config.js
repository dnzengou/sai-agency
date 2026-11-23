/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#9333ea",
          50: "#faf5ff",
          500: "#a855f7",
          600: "#9333ea",
          700: "#7e22ce",
          900: "#581c87",
        },
      },
    },
  },
  plugins: [],
};
