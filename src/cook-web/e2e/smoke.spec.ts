import {
  expect,
  Page,
  Request as PlaywrightRequest,
  Response,
  Route,
  TestInfo,
  test,
} from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

type ConsoleEntry = {
  type: string;
  text: string;
};

type NetworkEntry = {
  method: string;
  resourceType: string;
  status: number | null;
  url: string;
  requestId: string;
  harnessRunId: string;
};

const DEFAULT_PHONE = process.env.AI_SHIFU_TEST_PHONE || '13800138000';
const DEFAULT_OTP = process.env.AI_SHIFU_TEST_OTP || '1024';
const DEFAULT_CAPTCHA = process.env.AI_SHIFU_TEST_CAPTCHA || '0000';
const DEFAULT_GRAFANA_URL =
  process.env.AI_SHIFU_GRAFANA_URL || 'http://127.0.0.1:3001';
const DEFAULT_LOKI_URL =
  process.env.AI_SHIFU_LOKI_URL || 'http://127.0.0.1:3100';
const DEFAULT_TEMPO_URL =
  process.env.AI_SHIFU_TEMPO_URL || 'http://127.0.0.1:3200';
const DEFAULT_PROMETHEUS_URL =
  process.env.AI_SHIFU_PROMETHEUS_URL || 'http://127.0.0.1:9090';
const HARNESS_RUN_ID =
  process.env.AI_SHIFU_HARNESS_RUN_ID || `pw-run-${Date.now()}`;

const createRequestId = (testInfo: TestInfo) =>
  `pw-${Date.now()}-${testInfo.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 32)}`;

const ensurePhoneLoginVisible = async (page: Page) => {
  const phoneInput = page.locator('#phone');
  if (await phoneInput.isVisible()) {
    return phoneInput;
  }

  const tabs = page.getByRole('tab');
  const tabCount = await tabs.count();
  for (let index = 0; index < tabCount; index += 1) {
    await tabs.nth(index).click();
    if (await phoneInput.isVisible().catch(() => false)) {
      return phoneInput;
    }
  }

  await expect(phoneInput).toBeVisible();
  return phoneInput;
};

const buildObservabilityHints = (
  requestId: string,
  harnessRunId: string,
  diagnosticsPath?: string,
) => ({
  grafana: DEFAULT_GRAFANA_URL,
  loki: DEFAULT_LOKI_URL,
  tempo: DEFAULT_TEMPO_URL,
  prometheus: DEFAULT_PROMETHEUS_URL,
  requestId,
  harnessRunId,
  diagnosticsCommand: `cd src/api && python scripts/harness_diagnostics.py --request-id ${requestId}`,
  traceRunCommand: diagnosticsPath
    ? `python scripts/harness/trace_run.py --run-id ${harnessRunId} --request-id ${requestId} --browser-diagnostics ${diagnosticsPath}`
    : `python scripts/harness/trace_run.py --run-id ${harnessRunId} --request-id ${requestId}`,
});

const loginWithPhone = async (page: Page, redirectPath: string) => {
  await page.goto(`/login?redirect=${encodeURIComponent(redirectPath)}`);
  await expect(page.getByTestId('login-page')).toBeVisible();

  const phoneInput = await ensurePhoneLoginVisible(page);
  await phoneInput.fill(DEFAULT_PHONE);

  const termsCheckbox = page.locator('#terms');
  if (await termsCheckbox.isVisible()) {
    await termsCheckbox.click();
  }

  const captchaInput = page.getByTestId('captcha-input');
  await expect(captchaInput).toBeVisible();
  await captchaInput.fill(DEFAULT_CAPTCHA);

  const sendOtpButton = page
    .locator('#otp')
    .locator('xpath=ancestor::div[1]/following-sibling::button[1]');
  await sendOtpButton.click();

  const otpInput = page.locator('#otp');
  if (
    await page
      .getByRole('alertdialog')
      .isVisible()
      .catch(() => false)
  ) {
    const buttons = page.getByRole('alertdialog').getByRole('button');
    await buttons.last().click();
  }

  await expect(otpInput).toBeEnabled();
  await otpInput.fill(DEFAULT_OTP);
  await otpInput.press('Enter');
};

type CourseListItem = {
  bid?: unknown;
  slug?: unknown;
  is_guide_course?: unknown;
};

type CourseIdentity = {
  bid?: unknown;
  slug?: unknown;
  canonical_path?: unknown;
};

type BusinessEnvelope<T> = {
  code?: unknown;
  message?: unknown;
  data?: T;
};

const discoverDemoCourse = async (page: Page) => {
  const listResult = await page.evaluate(async () => {
    const rawToken = window.localStorage.getItem('token') || '';
    let token = rawToken;
    try {
      const parsedToken = JSON.parse(rawToken);
      if (typeof parsedToken === 'string') {
        token = parsedToken;
      }
    } catch {
      // The storage adapter can also persist an unquoted string.
    }

    const response = await fetch(
      '/api/shifu/shifus?page_index=1&page_size=100&archived=false',
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Token: token,
        },
      },
    );

    return {
      status: response.status,
      payload: await response.json(),
    };
  });

  expect(listResult.status).toBe(200);
  const payload = listResult.payload as BusinessEnvelope<{
    items?: CourseListItem[];
  }>;
  expect(payload.code, String(payload.message || '')).toBe(0);
  const courses = Array.isArray(payload.data?.items) ? payload.data.items : [];
  const guideCourses = courses.filter(item => item.is_guide_course && item.bid);
  if (guideCourses.length === 0) {
    throw new Error('Runtime harness did not expose a built-in guide course');
  }

  const probeFailures: string[] = [];
  for (const guideCourse of guideCourses) {
    const candidateBid = String(guideCourse.bid || '').trim();
    const probeResult = await page.evaluate(async bid => {
      const rawToken = window.localStorage.getItem('token') || '';
      let token = rawToken;
      try {
        const parsedToken = JSON.parse(rawToken);
        if (typeof parsedToken === 'string') {
          token = parsedToken;
        }
      } catch {
        // The storage adapter can also persist an unquoted string.
      }

      const response = await fetch(
        `/api/learn/shifu/${encodeURIComponent(bid)}?preview_mode=false`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            Token: token,
          },
        },
      );

      return {
        status: response.status,
        payload: await response.json(),
      };
    }, candidateBid);
    const probePayload =
      probeResult.payload as BusinessEnvelope<CourseIdentity>;
    if (probeResult.status !== 200 || probePayload.code !== 0) {
      probeFailures.push(
        `${candidateBid}: HTTP ${probeResult.status}, code ${String(probePayload.code)}, ${String(probePayload.message || '')}`,
      );
      continue;
    }

    const bid = String(probePayload.data?.bid || '').trim();
    const slug = String(probePayload.data?.slug || '').trim();
    if (!bid || !slug) {
      probeFailures.push(`${candidateBid}: canonical identity is incomplete`);
      continue;
    }

    expect(slug).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)+$/);
    return { bid, slug };
  }

  throw new Error(
    `Runtime harness did not expose a published guide course with a slug: ${probeFailures.join('; ')}`,
  );
};

const expectBusinessSuccess = async <T>(response: Response): Promise<T> => {
  expect(response.status(), response.url()).toBe(200);
  const payload = (await response.json()) as BusinessEnvelope<T>;
  expect(
    payload.code,
    `${response.url()}: ${String(payload.message || '')}`,
  ).toBe(0);
  return payload.data as T;
};

test.describe('agent-first smoke harness', () => {
  let consoleEntries: ConsoleEntry[] = [];
  let networkEntries: NetworkEntry[] = [];
  let lastObservedRequestId = '';

  test.beforeEach(async ({ page }, testInfo) => {
    consoleEntries = [];
    networkEntries = [];

    const requestId = createRequestId(testInfo);
    lastObservedRequestId = requestId;
    await page.context().setExtraHTTPHeaders({
      'X-Request-ID': requestId,
      'X-Harness-Run-ID': HARNESS_RUN_ID,
    });
    await page.addInitScript(harnessRunId => {
      (window as any).__HARNESS_RUN_ID__ = harnessRunId;
      window.sessionStorage.setItem('harness_run_id', String(harnessRunId));
    }, HARNESS_RUN_ID);

    page.on('console', message => {
      consoleEntries.push({
        type: message.type(),
        text: message.text(),
      });
      if (consoleEntries.length > 40) {
        consoleEntries = consoleEntries.slice(-40);
      }
    });

    page.on('response', async response => {
      const request = response.request();
      let headers: Record<string, string> = {};
      try {
        headers = await request.allHeaders();
      } catch {
        // Response callbacks can still settle while Playwright is closing the page.
        headers = {};
      }
      const requestIdHeader = headers['x-request-id'];
      if (requestIdHeader) {
        lastObservedRequestId = requestIdHeader;
      }
      networkEntries.push({
        method: request.method(),
        resourceType: request.resourceType(),
        status: response.status(),
        url: response.url(),
        requestId: requestIdHeader || lastObservedRequestId,
        harnessRunId: headers['x-harness-run-id'] || HARNESS_RUN_ID,
      });
      if (networkEntries.length > 60) {
        networkEntries = networkEntries.slice(-60);
      }
    });

    page.on('requestfailed', request => {
      networkEntries.push({
        method: request.method(),
        resourceType: request.resourceType(),
        status: null,
        url: request.url(),
        requestId: lastObservedRequestId,
        harnessRunId: HARNESS_RUN_ID,
      });
      if (networkEntries.length > 60) {
        networkEntries = networkEntries.slice(-60);
      }
    });
  });

  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status === testInfo.expectedStatus) {
      return;
    }

    await mkdir(testInfo.outputDir, { recursive: true });

    const screenshotPath = testInfo.outputPath('failure.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const diagnosticsPath = testInfo.outputPath('harness-diagnostics.json');
    await writeFile(
      diagnosticsPath,
      JSON.stringify(
        {
          pageUrl: page.url(),
          harnessRunId: HARNESS_RUN_ID,
          lastRequestId: lastObservedRequestId,
          console: consoleEntries,
          network: networkEntries.slice(-25),
          screenshot: screenshotPath,
          observability: buildObservabilityHints(
            lastObservedRequestId,
            HARNESS_RUN_ID,
            diagnosticsPath,
          ),
        },
        null,
        2,
      ),
      'utf-8',
    );
  });

  test('login flow reaches the admin main flow', async ({ page }) => {
    await loginWithPhone(page, '/admin/operations');
    await page.waitForURL('**/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
  });

  test('admin operations page loads', async ({ page }) => {
    await loginWithPhone(page, '/admin/operations');
    await page.waitForURL('**/admin/operations');
    await expect(page.getByTestId('admin-operations-header')).toBeVisible();
    await expect(page.getByTestId('admin-operations-filters')).toBeVisible();
  });

  test('legacy BID converges to the slug route before canonical learner requests start', async ({
    page,
  }) => {
    await loginWithPhone(page, '/admin/operations');
    await page.waitForURL('**/admin/operations');
    const { bid, slug } = await discoverDemoCourse(page);
    const encodedBid = encodeURIComponent(bid);
    const encodedSlug = encodeURIComponent(slug);
    const courseInfoResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === `/api/learn/shifu/${encodedBid}`;
    });
    const outlineResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return (
        url.pathname === `/api/learn/shifu/${encodedBid}/outline-item-tree`
      );
    });
    const legacyCoursePath = `/c/${encodedBid}?preview=false&mode=read&smoke=slug-e2e#canonical-link`;

    await page.goto(legacyCoursePath);
    const courseInfo = await expectBusinessSuccess<{
      bid?: string;
      slug?: string;
      canonical_path?: string;
    }>(await courseInfoResponse);
    expect(courseInfo).toMatchObject({
      bid,
      slug,
      canonical_path: `/c/${slug}`,
    });

    await expect
      .poll(() => new URL(page.url()).pathname)
      .toBe(`/c/${encodedSlug}`);
    const canonicalUrl = new URL(page.url());
    expect(canonicalUrl.searchParams.get('preview')).toBe('false');
    expect(canonicalUrl.searchParams.get('mode')).toBe('read');
    expect(canonicalUrl.searchParams.get('smoke')).toBe('slug-e2e');
    expect(canonicalUrl.hash).toBe('#canonical-link');
    await expect(page.getByTestId('course-chat-page')).toBeVisible();
    await expectBusinessSuccess(await outlineResponse);

    const slugCourseInfoResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === `/api/learn/shifu/${encodedSlug}`;
    });
    const canonicalOutlineAfterReload = page.waitForResponse(response => {
      const url = new URL(response.url());
      return (
        url.pathname === `/api/learn/shifu/${encodedBid}/outline-item-tree`
      );
    });

    let releaseSlugCourseInfo = () => {};
    const slugCourseInfoRelease = new Promise<void>(resolve => {
      releaseSlugCourseInfo = resolve;
    });
    let markSlugCourseInfoBlocked = () => {};
    const slugCourseInfoBlocked = new Promise<void>(resolve => {
      markSlugCourseInfoBlocked = resolve;
    });
    let bootstrapIsBlocked = false;
    const downstreamRequestsWhileBlocked: string[] = [];
    const recordBlockedLearnerRequest = (request: PlaywrightRequest) => {
      if (!bootstrapIsBlocked) {
        return;
      }
      const url = new URL(request.url());
      if (
        url.pathname.startsWith('/api/learn/') &&
        url.pathname !== `/api/learn/shifu/${encodedSlug}`
      ) {
        downstreamRequestsWhileBlocked.push(url.pathname);
      }
    };
    const holdSlugCourseInfo = async (route: Route) => {
      const url = new URL(route.request().url());
      if (
        url.pathname === `/api/learn/shifu/${encodedSlug}` &&
        url.searchParams.get('preview_mode') === 'false'
      ) {
        bootstrapIsBlocked = true;
        markSlugCourseInfoBlocked();
        await slugCourseInfoRelease;
      }
      await route.continue();
    };

    page.on('request', recordBlockedLearnerRequest);
    await page.route('**/api/learn/shifu/**', holdSlugCourseInfo);
    const reloadPromise = page.reload();
    await slugCourseInfoBlocked;
    await reloadPromise;
    await page.evaluate(
      () =>
        new Promise<void>(resolve => {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
        }),
    );
    const blockedRequestSnapshot = [...downstreamRequestsWhileBlocked];
    bootstrapIsBlocked = false;
    releaseSlugCourseInfo();

    const directSlugCourseInfo = await expectBusinessSuccess<{
      bid?: string;
      slug?: string;
    }>(await slugCourseInfoResponse);
    await page.unroute('**/api/learn/shifu/**', holdSlugCourseInfo);
    page.off('request', recordBlockedLearnerRequest);
    expect(blockedRequestSnapshot).toEqual([]);
    expect(directSlugCourseInfo).toMatchObject({ bid, slug });
    await expect(page.getByTestId('course-chat-page')).toBeVisible();
    await expectBusinessSuccess(await canonicalOutlineAfterReload);
    expect(new URL(page.url()).pathname).toBe(`/c/${encodedSlug}`);
  });
});
