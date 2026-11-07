import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' para que el bundle funcione desde el bucket S3 sin rutas absolutas
export default defineConfig({
  plugins: [react()],
  base: './',
});