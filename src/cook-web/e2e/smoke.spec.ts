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
  harnessRunId: string;
};

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
const HARNESS_RUN_ID =
  process.env.AI_SHIFU_HARNESS_RUN_ID || `pw-run-${Date.now()}`;

const createRequestId = (testInfo: TestInfo) =>
  `pw-${Date.now()}-${testInfo.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 32)}`;

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

const isAdminCourseResponse = (url: string) => {
  const pathname = new URL(url).pathname;
  return pathname.endsWith('/shifu/admin/operations/courses');
};

const waitForAdminCourseData = async (page: Page, entries: NetworkEntry[]) => {
  if (
    entries.some(
      entry =>
        entry.status !== null &&
        entry.url.includes('/api/') &&
        isAdminCourseResponse(entry.url),
    )
  ) {
    return;
  }

  await page.waitForResponse(
    response => isAdminCourseResponse(response.url()),
    {
      timeout: 20_000,
    },
  );
};

const expectNoServerErrors = (serverErrorEntries: NetworkEntry[]) => {
  expect(serverErrorEntries).toEqual([]);
};

test.describe('agent-first smoke harness', () => {
  let consoleEntries: ConsoleEntry[] = [];
  let networkEntries: NetworkEntry[] = [];
  let serverErrorEntries: NetworkEntry[] = [];
  let lastObservedRequestId = '';

  test.beforeEach(async ({ page }, testInfo) => {
    consoleEntries = [];
    networkEntries = [];
    serverErrorEntries = [];

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

    page.on('response', response => {
      const request = response.request();
      const headers = request.headers();
      const requestIdHeader = headers['x-request-id'];
      if (requestIdHeader) {
        lastObservedRequestId = requestIdHeader;
      }
      const entry = {
        method: request.method(),
        resourceType: request.resourceType(),
        status: response.status(),
        url: response.url(),
        requestId: requestIdHeader || lastObservedRequestId,
        harnessRunId: headers['x-harness-run-id'] || HARNESS_RUN_ID,
      };
      networkEntries.push(entry);
      if (entry.url.includes('/api/') && entry.status >= 500) {
        serverErrorEntries.push(entry);
      }
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

  test('authenticated admin operations page loads without server errors', async ({
    page,
  }) => {
    await page.goto('/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    await expect(page.getByTestId('admin-operations-header')).toBeVisible();
    await expect(page.getByTestId('admin-operations-filters')).toBeVisible();
    await waitForAdminCourseData(page, networkEntries);
    expectNoServerErrors(serverErrorEntries);
  });

  test('learner course shell loads its first data request without server errors', async ({
    page,
  }) => {
    const coursePath = `/c/${DEFAULT_DEMO_SHIFU_BID}`;
    await page.goto(coursePath);
    await expect(page.getByTestId('course-chat-page')).toBeVisible();
    await waitForCourseData(page, networkEntries);
    expectNoServerErrors(serverErrorEntries);
  });
});
