/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * 배포 경로(base)를 결정하는 유일한 곳.
 * - BASE_PATH 환경변수가 있으면 그대로 사용 (예: /saicerti/). GitHub Actions에서는 configure-pages의 base_path를 넘긴다.
 * - 없으면 '/' (로컬 개발)
 */
function resolveBase(raw: string | undefined): string {
  if (!raw || raw === '/') return '/';
  let b = raw.trim();
  if (!b.startsWith('/')) b = '/' + b;
  if (!b.endsWith('/')) b = b + '/';
  return b;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  if (mode === 'production' && env.VITE_ENABLE_DEMO === 'true') {
    throw new Error('운영(production) 빌드에서는 VITE_ENABLE_DEMO=true를 사용할 수 없습니다. 개발 데모는 npm run dev에서만 사용하세요.');
  }
  return {
    base: resolveBase(env.BASE_PATH),
    plugins: [react()],
    build: { target: 'es2022', sourcemap: false, chunkSizeWarningLimit: 900 },
    server: { port: 5174, strictPort: true },
    preview: { port: 4174, strictPort: true },
    test: {
      include: ['tests/unit/**/*.test.{ts,tsx}'],
      environment: 'node',
      testTimeout: 60000,
    },
  };
});
