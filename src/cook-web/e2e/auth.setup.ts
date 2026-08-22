import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

import { attachRuntimeHarnessDiagnostics } from './harness-diagnostics';
import { loginWithPhone } from './harness-auth';

const authStatePath = 'playwright/.auth/runtime-harness-user.json';

test('runtime harness authenticates the shared test user', async ({
  page,
}, testInfo) => {
  const diagnostics = await attachRuntimeHarnessDiagnostics(page, testInfo);

  try {
    await loginWithPhone(page, '/admin/operations');
    await page.waitForURL('**/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    await mkdir('playwright/.auth', { recursive: true });
    await page.context().storageState({ path: authStatePath });
  } finally {
    await diagnostics.captureFailure(testInfo);
  }
});
