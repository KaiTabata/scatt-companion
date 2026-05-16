import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // ビルド出力先: ../docs (GitHub Pages が docs/ を配信)
  outDir: '../docs',
  // content store などの中間ファイルが outDir に混入しないように分離
  cacheDir: './node_modules/.astro',

  // GitHub Pages: https://kaitabata.github.io/scatt-companion/
  site: 'https://kaitabata.github.io',
  base: '/scatt-companion',

  trailingSlash: 'ignore',

  vite: {
    plugins: [tailwindcss()],
  },
});
