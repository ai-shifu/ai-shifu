import { expect, Page, TestInfo, test } from '@playwright/test';
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
};

const DEFAULT_PHONE = process.env.AI_SHIFU_TEST_PHONE || '13800138000';
const DEFAULT_OTP = process.env.AI_SHIFU_TEST_OTP || '1024';
const DEFAULT_DEMO_SHIFU_BID =
  process.env.AI_SHIFU_DEMO_SHIFU_BID || 'b5d7844387e940ed9480a6f945a6db6a';
const DEFAULT_GRAFANA_URL =
  process.env.AI_SHIFU_GRAFANA_URL || 'http://127.0.0.1:3001';
const DEFAULT_LOKI_URL =
  process.env.AI_SHIFU_LOKI_URL || 'http://127.0.0.1:3100';
const DEFAULT_TEMPO_URL =
  process.env.AI_SHIFU_TEMPO_URL || 'http://127.0.0.1:3200';
const DEFAULT_PROMETHEUS_URL =
  process.env.AI_SHIFU_PROMETHEUS_URL || 'http://127.0.0.1:9090';

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

const buildObservabilityHints = (requestId: string) => ({
  grafana: DEFAULT_GRAFANA_URL,
  loki: DEFAULT_LOKI_URL,
  tempo: DEFAULT_TEMPO_URL,
  prometheus: DEFAULT_PROMETHEUS_URL,
  requestId,
  diagnosticsCommand: `cd src/api && python scripts/harness_diagnostics.py --request-id ${requestId}`,
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

const waitForCourseData = async (page: Page, entries: NetworkEntry[]) => {
  if (
    entries.some(
      entry =>
        entry.url.includes('/api/') &&
        (entry.url.includes('/shifu/') || entry.url.includes('/learn/')) &&
        entry.status !== null,
    )
  ) {
    return;
  }

  await page.waitForResponse(
    response =>
      response.url().includes('/api/') &&
      (response.url().includes('/shifu/') ||
        response.url().includes('/learn/')),
    { timeout: 20_000 },
  );
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
    });

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
      const headers = await request.allHeaders();
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
          lastRequestId: lastObservedRequestId,
          console: consoleEntries,
          network: networkEntries.slice(-25),
          screenshot: screenshotPath,
          observability: buildObservabilityHints(lastObservedRequestId),
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

  test('learner chat shell renders and completes the first key request', async ({
    page,
  }) => {
    const coursePath = `/c/${DEFAULT_DEMO_SHIFU_BID}`;
    await loginWithPhone(page, coursePath);
    await page.waitForURL(`**${coursePath}`);
    await expect(page.getByTestId('course-chat-page')).toBeVisible();
    await waitForCourseData(page, networkEntries);
  });
});
