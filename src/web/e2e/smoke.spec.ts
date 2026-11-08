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
      response =>
        matchesCourseRequest(response.url(), 'false') && response.ok(),
      { timeout: 20_000 },
    ),
    page.waitForResponse(
      response => matchesCourseRequest(response.url(), 'true') && response.ok(),
      { timeout: 20_000 },
    ),
    page.waitForResponse(
      response =>
        new URL(response.url()).pathname === outlinePath && response.ok(),
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

  test('saves the first learning mode selected from the course page', async ({
    page,
  }) => {
    const courseId = DEFAULT_DEMO_SHIFU_BID;
    const coursePath = `/c/${courseId}`;
    const storageKey = `course_learning_mode:${courseId}`;

    // Enable the Listen option independently of the demo course configuration.
    await page.route(
      url => url.pathname === `/api/learn/shifu/${courseId}`,
      async route => {
        const response = await route.fetch();
        const payload = await response.json();
        await route.fulfill({
          response,
          json: {
            ...payload,
            data: {
              ...payload.data,
              tts_enabled: true,
              default_listen_mode_enabled: false,
            },
          },
        });
      },
    );

    const learnerBootstrap = waitForLearnerBootstrap(page, courseId);
    await page.goto(coursePath);
    await learnerBootstrap;
    const read = page.getByRole('radio', { name: /^(Read|阅读)$/ });
    const listen = page.getByRole('radio', { name: /^(Listen|听课)$/ });
    await expect(read).toBeChecked();
    expect(
      await page.evaluate(key => localStorage.getItem(key), storageKey),
    ).toBeNull();

    await listen.click();
    await expect(page).toHaveURL(
      url => url.searchParams.get('mode') === 'listen',
    );
    await expect
      .poll(() => page.evaluate(key => localStorage.getItem(key), storageKey))
      .toBe('listen');

    await page.goto(coursePath);
    await expect(listen).toBeChecked();
  });
});
