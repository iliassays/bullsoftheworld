import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tailwind + shadcn/ui get added in build step 3.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
