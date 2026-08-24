import { defineConfig } from '@playwright/test';

const baseURL = process.env.AI_SHIFU_BASE_URL || 'http://localhost:8080';
const authStatePath = 'playwright/.auth/runtime-harness-user.json';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'runtime-harness-auth',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'runtime-harness-smoke',
      testMatch: /smoke\.spec\.ts/,
      dependencies: ['runtime-harness-auth'],
      use: {
        storageState: authStatePath,
      },
    },
    {
      name: 'e2e',
      testIgnore: [/auth\.setup\.ts/, /smoke\.spec\.ts/],
    },
  ],
});
