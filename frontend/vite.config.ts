import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** Where `langgraph dev` serves the agent server. */
const AGENT_SERVER = 'http://localhost:2024'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The browser talks to the agent server same-origin, so CORS never comes
      // up; production puts a real proxy on the same path.
      '/langgraph': {
        target: AGENT_SERVER,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/langgraph/, ''),
      },
    },
  },
})
