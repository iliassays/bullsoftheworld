import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("lightweight-charts")) return "vendor-charts";
          if (id.includes("node_modules/react") || id.includes("react-router")) {
            return "vendor-react";
          }
        },
      },
    },
  },
  // PORT lets a preview harness assign a free port when 5173 is taken; default unchanged.
  server: { port: Number(process.env.PORT) || 5173 },
});
