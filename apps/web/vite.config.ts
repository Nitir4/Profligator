import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const { PROFLIGATOR_API_PORT = "8000" } = loadEnv(mode, ".", "PROFLIGATOR_API_PORT");
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": `http://127.0.0.1:${PROFLIGATOR_API_PORT}`,
      },
    },
  };
});
