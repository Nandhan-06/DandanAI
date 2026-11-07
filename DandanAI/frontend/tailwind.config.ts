import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: { colors: { ink: { 50: "#f6f7f9", 100: "#eceef2", 200: "#d5d9e1", 500: "#5b6475", 700: "#2b3345", 900: "#12182a" }, brand: { 50: "#eef4ff", 100: "#d9e6ff", 500: "#2f5fd0", 600: "#2449a8", 700: "#1c3a86" }, gold: { 500: "#b8860b" } },
    fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], serif: ["Georgia", "ui-serif", "serif"] } } },
  plugins: [],
} satisfies Config;
