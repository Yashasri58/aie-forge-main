import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/",
  server: {
    port: 5173,
    proxy: {
      "/health":   "http://localhost:8000",
      "/services": "http://localhost:8000",
      "/graph":    "http://localhost:8000",
      "/impact":   "http://localhost:8000",
      "/pipeline": "http://localhost:8000",
      "/codegen":  "http://localhost:8000",
      "/cache":    "http://localhost:8000",
      "/reverse":  "http://localhost:8000",
      "/chat":     "http://localhost:8000",
    },
  },
  build: {
    outDir: resolve(__dirname, "./dist"),
    emptyOutDir: true,
  },
});
