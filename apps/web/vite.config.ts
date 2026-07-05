import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // PORT lets a preview harness assign a free port when 5173 is taken; default unchanged.
  server: { port: Number(process.env.PORT) || 5173 },
});
