import { type BrowserContext, expect, Page, test } from '@playwright/test';

import { loginWithPhone } from './harness-auth';
import {
  attachRuntimeHarnessDiagnostics,
  type RuntimeHarnessDiagnostics,
} from './harness-diagnostics';

type Outline = { bid: string; children: Outline[]; type: string };
type Memory = { value_id: string; key: string; value: string };

const source =
  'Choose a learning path.\n\n?[{{e2e_answer}} Visible A//a | Visible B//b]';

const callApi = async <T>(
  page: Page,
  method: string,
  path: string,
  data?: Record<string, unknown>,
): Promise<T> => {
  const token = await page.evaluate<string>(() =>
    JSON.parse(window.localStorage.getItem('token') || '""'),
  );
  expect(token).not.toBe('');
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: {
      Authorization: `Bearer ${token}`,
      Token: token,
      'Accept-Language': 'en-US',
    },
  });
  expect(response.ok(), `${method} ${path}`).toBe(true);
  const body = await response.json();
  expect(body.code, `${method} ${path}: ${body.message}`).toBe(0);
  return body.data;
};

test.describe('standard interaction binding persistence', () => {
  let diagnostics: RuntimeHarnessDiagnostics;
  let learnerContext: BrowserContext | undefined;

  test.beforeEach(async ({ page }, testInfo) => {
    learnerContext = undefined;
    diagnostics = await attachRuntimeHarnessDiagnostics(page, testInfo);
  });

  test.afterEach(async ({}, testInfo) => {
    try {
      await diagnostics.captureFailure(testInfo);
    } finally {
      await learnerContext?.close();
    }
  });

  test('author edits and saves a binding, a learner answers, then reloads it', async ({
    page,
    browser,
    baseURL,
  }, testInfo) => {
    test.setTimeout(120_000);
    await page.goto('/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    const onboarding = await callApi<{
      scenes: Record<string, { eligible: boolean; status: string | null }>;
    }>(page, 'GET', '/api/user/onboarding/status');
    if (onboarding.scenes.course_editor_onboarding?.eligible) {
      await callApi(page, 'POST', '/api/user/onboarding/complete', {
        scene_key: 'course_editor_onboarding',
        trigger_source: 'editor_entry',
        status: 'skipped',
      });
    }
    const course = await callApi<{ bid: string }>(
      page,
      'PUT',
      '/api/shifu/shifus',
      {
        name: 'Standard binding regression',
        description: 'Runtime test course',
      },
    );
    const coursePath = `/api/shifu/shifus/${course.bid}`;
    const outlines = await callApi<Outline[]>(
      page,
      'GET',
      `${coursePath}/outlines`,
    );
    const lesson = outlines[0]?.children[0];
    expect(lesson?.type).toBe('trial');
    const contentPath = `${coursePath}/outlines/${lesson.bid}/mdflow`;

    await page.goto(`/shifu/${course.bid}?lessonid=${lesson.bid}`);
    await page.getByRole('tab', { name: 'Pro', exact: true }).click();
    const editor = page.locator('.cm-content[contenteditable="true"]');
    await expect(editor).toBeVisible();
    const saved = page.waitForResponse(response => {
      if (
        new URL(response.url()).pathname !== contentPath ||
        response.request().method() !== 'POST'
      ) {
        return false;
      }
      return response.request().postDataJSON()?.data === source;
    });
    await editor.fill(source);
    expect((await (await saved).json()).code).toBe(0);
    expect(await callApi<string>(page, 'GET', contentPath)).toBe(source);
    await page.reload();
    await page.getByRole('tab', { name: 'Pro', exact: true }).click();
    await expect(editor).toHaveText(source, { useInnerText: true });
    await callApi(page, 'POST', `${coursePath}/publish`);

    // A separate browser context cannot reuse the author's UI or preview state.
    learnerContext = await browser.newContext({
      baseURL,
      locale: 'en-US',
    });
    const learner = await learnerContext.newPage();
    diagnostics = await attachRuntimeHarnessDiagnostics(learner, testInfo);
    await loginWithPhone(
      learner,
      `/c/${course.bid}?lessonid=${lesson.bid}`,
      process.env.AI_SHIFU_LEARNER_TEST_PHONE || '13800138001',
    );
    await expect(learner.getByTestId('course-chat-page')).toBeVisible();
    const memoryPath = `/api/user/course-memory?course_id=${course.bid}`;
    const readAnswer = async () =>
      (
        await callApi<{ items: Memory[] }>(learner, 'GET', memoryPath)
      ).items.find(item => item.key === 'e2e_answer');
    expect(await readAnswer()).toBeUndefined();

    const choice = learner.getByText('Visible B', { exact: true });
    await expect(choice).toBeVisible({ timeout: 30_000 });
    const submitted = learner.waitForRequest(request => {
      const url = new URL(request.url());
      return (
        url.pathname === `/api/learn/shifu/${course.bid}/run/${lesson.bid}` &&
        url.searchParams.get('preview_mode') === 'false' &&
        request.method() === 'PUT'
      );
    });
    await choice.click();
    expect((await submitted).postDataJSON().input).toEqual({
      e2e_answer: ['b'],
    });
    await expect.poll(async () => (await readAnswer())?.value).toBe('b');
    const persisted = await readAnswer();
    expect(persisted?.value_id).toBeTruthy();

    const history = learner.waitForResponse(response => {
      const url = new URL(response.url());
      return (
        url.pathname ===
          `/api/learn/shifu/${course.bid}/records/${lesson.bid}` &&
        url.searchParams.get('preview_mode') === 'false' &&
        response.ok()
      );
    });
    await learner.reload();
    expect((await (await history).json()).code).toBe(0);
    // Historical answers remain editable; reload must retain the chosen value.
    await expect(choice).toHaveClass(/(?:^|\s)select(?:\s|$)/);
    await expect(
      learner.getByText('Visible A', { exact: true }),
    ).not.toHaveClass(/(?:^|\s)select(?:\s|$)/);
    expect(await readAnswer()).toEqual(persisted);
  });
});
