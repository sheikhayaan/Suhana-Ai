import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    outDir: 'static/react',
    emptyOutDir: false,
    minify: true,
    lib: {
      entry: 'src/suhana-hero.jsx',
      formats: ['iife'],
      name: 'SuhanaHeroBundle',
      cssFileName: 'suhana-hero',
      fileName: () => 'suhana-hero.js'
    }
  }
});
