import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

import {
  attachRuntimeHarnessDiagnostics,
  type RuntimeHarnessDiagnostics,
} from './harness-diagnostics';
import {
  initializeLocalAdmin,
  loginWithLocalAdmin,
  loginWithPhone,
} from './harness-auth';

const authStatePath = 'playwright/.auth/runtime-harness-user.json';

let diagnostics: RuntimeHarnessDiagnostics | undefined;

test.beforeEach(async ({ page }, testInfo) => {
  diagnostics = undefined;
  diagnostics = await attachRuntimeHarnessDiagnostics(page, testInfo);
});

test.afterEach(async ({}, testInfo) => {
  await diagnostics?.captureFailure(testInfo);
});

test('runtime harness initializes and signs in the local administrator', async ({
  page,
}) => {
  await initializeLocalAdmin(page);
  const status = await (
    await page.request.get('/api/installation/status')
  ).json();
  expect(status.data).toEqual({
    setup_required: false,
    local_admin_login_enabled: true,
  });
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload();
  await loginWithLocalAdmin(page);
  await page.goto('/admin/operations');
  await expect(page.getByTestId('admin-operations-page')).toBeVisible();
  await mkdir('playwright/.auth', { recursive: true });
  await page.context().storageState({ path: authStatePath });
});

test('runtime harness retains ordinary phone authentication without administrator promotion', async ({
  page,
}) => {
  const authenticated = page.waitForResponse(
    response => new URL(response.url()).pathname === '/api/user/login_sms',
  );
  const courseId =
    process.env.AI_SHIFU_DEMO_SHIFU_BID || 'b5d7844387e940ed9480a6f945a6db6a';
  await loginWithPhone(page, `/c/${courseId}`);
  const payload = await (await authenticated).json();
  expect(payload.code).toBe(0);
  expect(payload.data.userInfo.is_operator).toBeFalsy();
});
