import { expect, Page, test } from '@playwright/test';

import { callHarnessApi } from './harness-auth';
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

  test('opens the guide course learning page in a new tab from its admin card', async ({
    page,
    context,
  }) => {
    await page.goto('/admin');
    const guideCard = page.locator(
      '[data-onboarding-id^="guide-course-card-"]',
    );
    const editorLink = guideCard.getByRole('link');
    await expect(editorLink).toHaveAttribute('href', /^\/shifu\/[^/?#]+$/);
    const learnerPath = (await editorLink.getAttribute('href'))?.replace(
      /^\/shifu\//,
      '/c/',
    );

    await guideCard.getByRole('button', { name: /^(More|更多)$/ }).click();
    const learningLink = page.getByRole('menuitem', {
      name: /^(Open learning page|打开学习页面)$/,
    });
    const [learningPage] = await Promise.all([
      context.waitForEvent('page'),
      learningLink.click(),
    ]);

    await expect(learningPage).toHaveURL(url => url.pathname === learnerPath);
    await expect(page).toHaveURL(url => url.pathname === '/admin');
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
    await page.goto('/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    const { bid: courseId } = await callHarnessApi<{ bid: string }>(
      page,
      'PUT',
      '/api/shifu/shifus',
      {
        name: 'Learning mode preference regression',
        description: 'Runtime test course',
      },
    );
    const editorPath = `/api/shifu/shifus/${courseId}`;
    const outlines = await callHarnessApi<{ children: { bid: string }[] }[]>(
      page,
      'GET',
      `${editorPath}/outlines`,
    );
    const lesson = outlines[0].children[0];
    await callHarnessApi(
      page,
      'POST',
      `${editorPath}/outlines/${lesson.bid}/mdflow`,
      { data: 'Review the course learning modes.' },
    );
    await callHarnessApi(page, 'POST', `${editorPath}/publish`);

    const coursePath = `/c/${courseId}`;
    const storageKey = `course_learning_mode:${courseId}`;

    // Enable the Listen option independently of TTS provider configuration.
    await page.route(
      url => url.pathname === `/api/learn/shifu/${courseId}`,
      async route => {
        const response = await route.fetch();
        const payload = await response.json();
        if (payload.code !== 0) {
          await route.fulfill({ response });
          return;
        }
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
    for (const response of await learnerBootstrap) {
      expect((await response.json()).code).toBe(0);
    }
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
