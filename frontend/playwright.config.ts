import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:5174', trace: 'retain-on-failure' },
  webServer: [
    { command: '.venv/bin/harnesslab serve --port 8001', url: 'http://127.0.0.1:8001/api/health', cwd: '..', env: { HARNESSLAB_DATABASE_URL: '.harnesslab/browser-tests.db' } },
    { command: 'pnpm dev --port 5174', url: 'http://127.0.0.1:5174', env: { HARNESSLAB_API_TARGET: 'http://127.0.0.1:8001' } }
  ]
});
