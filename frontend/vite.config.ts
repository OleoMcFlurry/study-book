import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/static/dist/",
  build: {
    emptyOutDir: true,
    outDir: "../src/knowledge_path_demo/static/dist",
  },
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
