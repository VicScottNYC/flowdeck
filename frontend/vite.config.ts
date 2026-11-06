import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = process.env.FLOWDECK_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': API,
      '/fhir': API,
      '/ws': { target: API.replace('http', 'ws'), ws: true },
    },
  },
})
