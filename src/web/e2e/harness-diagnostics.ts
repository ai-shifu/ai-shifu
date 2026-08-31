import type { Page, TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

export type ConsoleEntry = {
  type: string;
  text: string;
};

export type NetworkEntry = {
  method: string;
  resourceType: string;
  status: number | null;
  url: string;
  requestId: string;
  harnessRunId: string;
};

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
  diagnosticsPath: string,
) => ({
  requestId,
  harnessRunId: HARNESS_RUN_ID,
  browserDiagnostics: diagnosticsPath,
  composeLog: 'artifacts/runtime-harness/compose.log',
  composeStatus: 'artifacts/runtime-harness/compose-ps.json',
  investigation: 'Review the uploaded runtime-harness-artifacts bundle.',
});

export type RuntimeHarnessDiagnostics = {
  captureFailure: (testInfo: TestInfo) => Promise<void>;
  networkEntries: NetworkEntry[];
  serverErrorEntries: NetworkEntry[];
};

export const attachRuntimeHarnessDiagnostics = async (
  page: Page,
  testInfo: TestInfo,
): Promise<RuntimeHarnessDiagnostics> => {
  const consoleEntries: ConsoleEntry[] = [];
  const networkEntries: NetworkEntry[] = [];
  const serverErrorEntries: NetworkEntry[] = [];
  let lastObservedRequestId = createRequestId(testInfo);

  await page.context().setExtraHTTPHeaders({
    'X-Request-ID': lastObservedRequestId,
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
      consoleEntries.splice(0, consoleEntries.length - 40);
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
      networkEntries.splice(0, networkEntries.length - 60);
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
      networkEntries.splice(0, networkEntries.length - 60);
    }
  });

  return {
    networkEntries,
    serverErrorEntries,
    async captureFailure(failedTestInfo: TestInfo) {
      if (failedTestInfo.status === failedTestInfo.expectedStatus) {
        return;
      }

      await mkdir(failedTestInfo.outputDir, { recursive: true });
      const screenshotPath = failedTestInfo.outputPath('failure.png');
      let screenshotError: string | undefined;
      try {
        await page.screenshot({ path: screenshotPath, fullPage: true });
      } catch (error) {
        screenshotError =
          error instanceof Error ? error.message : String(error);
      }
      const diagnosticsPath = failedTestInfo.outputPath(
        'harness-diagnostics.json',
      );
      await writeFile(
        diagnosticsPath,
        JSON.stringify(
          {
            pageUrl: page.url(),
            harnessRunId: HARNESS_RUN_ID,
            lastRequestId: lastObservedRequestId,
            console: consoleEntries,
            network: networkEntries.slice(-25),
            screenshot: screenshotError ? undefined : screenshotPath,
            screenshotError,
            runtimeHarness: buildRuntimeHarnessHints(
              lastObservedRequestId,
              diagnosticsPath,
            ),
          },
          null,
          2,
        ),
        'utf-8',
      );
    },
  };
};
