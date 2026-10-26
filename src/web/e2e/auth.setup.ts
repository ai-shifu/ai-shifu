import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

import {
  attachRuntimeHarnessDiagnostics,
  type RuntimeHarnessDiagnostics,
} from './harness-diagnostics';
import { loginWithPhone } from './harness-auth';

const authStatePath = 'playwright/.auth/runtime-harness-user.json';

let diagnostics: RuntimeHarnessDiagnostics | undefined;

test.beforeEach(async ({ page }, testInfo) => {
  diagnostics = undefined;
  diagnostics = await attachRuntimeHarnessDiagnostics(page, testInfo);
});

test.afterEach(async ({}, testInfo) => {
  await diagnostics?.captureFailure(testInfo);
});

test('runtime harness authenticates the shared test user', async ({ page }) => {
  await loginWithPhone(page, '/admin/operations');
  await page.waitForURL('**/admin/operations');
  await expect(page.getByTestId('admin-operations-page')).toBeVisible();
  await mkdir('playwright/.auth', { recursive: true });
  await page.context().storageState({ path: authStatePath });
});
