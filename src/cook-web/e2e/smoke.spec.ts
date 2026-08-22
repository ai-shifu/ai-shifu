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
const HARNESS_RUN_ID =
  process.env.AI_SHIFU_HARNESS_RUN_ID || `pw-run-${Date.now()}`;

const createRequestId = (testInfo: TestInfo) =>
  `pw-${Date.now()}-${testInfo.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 32)}`;

const buildRuntimeHarnessHints = (
  requestId: string,
  harnessRunId: string,
  diagnosticsPath: string,
) => ({
  requestId,
  harnessRunId,
  browserDiagnostics: diagnosticsPath,
  composeLog: 'artifacts/runtime-harness/compose.log',
  composeStatus: 'artifacts/runtime-harness/compose-ps.json',
  investigation: 'Review the uploaded runtime-harness-artifacts bundle.',
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
          runtimeHarness: buildRuntimeHarnessHints(
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
    const adminBootstrap = waitForAdminBootstrap(page);
    await page.goto('/admin/operations');
    await expect(page.getByTestId('admin-operations-page')).toBeVisible();
    await expect(page.getByTestId('admin-operations-header')).toBeVisible();
    await expect(page.getByTestId('admin-operations-filters')).toBeVisible();
    await adminBootstrap;
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
