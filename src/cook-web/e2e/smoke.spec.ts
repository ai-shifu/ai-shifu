import { expect, Page, test } from '@playwright/test';

import {
  attachRuntimeHarnessDiagnostics,
  type NetworkEntry,
  type RuntimeHarnessDiagnostics,
} from './harness-diagnostics';

const DEFAULT_DEMO_SHIFU_BID =
  process.env.AI_SHIFU_DEMO_SHIFU_BID || 'b5d7844387e940ed9480a6f945a6db6a';

const waitForLearnerBootstrap = (page: Page, courseId: string) => {
  const coursePath = `/api/learn/shifu/${courseId}`;
  const outlinePath = `${coursePath}/outline-item-tree`;
  const matchesCourseRequest = (url: string, previewMode: string) => {
    const parsedUrl = new URL(url);
    return (
      parsedUrl.pathname === coursePath &&
      parsedUrl.searchParams.get('preview_mode') === previewMode
    );
  };

  return Promise.all([
    page.waitForResponse(
      response => matchesCourseRequest(response.url(), 'false'),
      { timeout: 20_000 },
    ),
    page.waitForResponse(
      response => matchesCourseRequest(response.url(), 'true'),
      { timeout: 20_000 },
    ),
    page.waitForResponse(
      response => new URL(response.url()).pathname === outlinePath,
      { timeout: 20_000 },
    ),
  ]);
};

const ADMIN_BOOTSTRAP_PATHS = [
  '/api/shifu/admin/operations/courses',
  '/api/shifu/admin/operations/courses/overview',
  '/api/llm/model-list',
  '/api/shifu/tts/config',
];

const waitForAdminBootstrap = (page: Page) =>
  Promise.all(
    ADMIN_BOOTSTRAP_PATHS.map(pathname =>
      page.waitForResponse(
        response => new URL(response.url()).pathname === pathname,
        { timeout: 20_000 },
      ),
    ),
  );

const expectNoServerErrors = (serverErrorEntries: NetworkEntry[]) => {
  expect(serverErrorEntries).toEqual([]);
};

test.describe('agent-first smoke harness', () => {
  let diagnostics: RuntimeHarnessDiagnostics;

  test.beforeEach(async ({ page }, testInfo) => {
    diagnostics = await attachRuntimeHarnessDiagnostics(page, testInfo);
  });

  test.afterEach(async ({}, testInfo) => {
    await diagnostics.captureFailure(testInfo);
  });

  test('authenticated admin operations page loads without server errors', async ({
    page,
  }) => {
    const adminBootstrap = waitForAdminBootstrap(page);
    await page.goto('/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    await expect(page.getByTestId('admin-operations-header')).toBeVisible();
    await expect(page.getByTestId('admin-operations-filters')).toBeVisible();
    await adminBootstrap;
    expectNoServerErrors(diagnostics.serverErrorEntries);
  });

  test('learner course shell loads its first data request without server errors', async ({
    page,
  }) => {
    const learnerBootstrap = waitForLearnerBootstrap(
      page,
      DEFAULT_DEMO_SHIFU_BID,
    );
    await page.goto(`/c/${DEFAULT_DEMO_SHIFU_BID}`);
    await expect(page.getByTestId('course-chat-page')).toBeVisible();
    await learnerBootstrap;
    expectNoServerErrors(diagnostics.serverErrorEntries);
  });
});
