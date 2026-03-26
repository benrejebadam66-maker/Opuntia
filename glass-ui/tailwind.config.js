/** @type {import('tailwindcss').Config} */
import forms from "@tailwindcss/forms";
import typography from "@tailwindcss/typography";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        glass: "rgba(255,255,255,0.1)",
      },
      boxShadow: {
        ambient: "0 30px 80px rgba(0,0,0,0.35)",
        glass: "0 20px 60px rgba(0,0,0,0.25)",
      },
      backdropBlur: {
        glass: "30px",
      },
    },
  },
  plugins: [forms, typography],
};
