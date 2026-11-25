import { spawn, spawnSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import type { Readable } from 'node:stream';

import { expect, Page } from '@playwright/test';

const DEFAULT_PHONE = process.env.AI_SHIFU_TEST_PHONE || '13800138000';
const DEFAULT_OTP = process.env.AI_SHIFU_TEST_OTP || '1024';
const DEFAULT_CAPTCHA = process.env.AI_SHIFU_TEST_CAPTCHA || '0000';
const ADMIN_USERNAME = 'admin';
// The API service of both the development and the runtime-harness stacks.
const API_SERVICE = 'ai-shifu-api-dev';
// A generated password is one run of letters and digits. The line printed for
// a configured BOOTSTRAP_ADMIN_PASSWORD contains spaces and never matches.
const BOOTSTRAP_PASSWORD_LINE = /^\s*Password: ([A-Za-z0-9]+)\s*$/;

const runDocker = (args: string[]) => {
  const result = spawnSync('docker', args, { encoding: 'utf8' });
  if (result.error || result.status !== 0) {
    throw new Error(
      `docker ${args[0]} failed: ${result.error?.message || result.stderr}`,
    );
  }
  // Only stdout: a CLI warning on stderr must not count as a container ID.
  return result.stdout;
};

// Stream the container log line by line, so a long-running stack's log is never
// held in memory, and keep the password from the last banner.
const readLoggedPassword = (container: string) =>
  new Promise<string>((resolve, reject) => {
    const child = spawn('docker', ['logs', container], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let password = '';
    const scan = (stream: Readable) => {
      createInterface({ input: stream, crlfDelay: Infinity }).on(
        'line',
        line => {
          const match = BOOTSTRAP_PASSWORD_LINE.exec(line);
          if (match) {
            password = match[1];
          }
        },
      );
    };
    scan(child.stdout);
    scan(child.stderr);
    child.on('error', error =>
      reject(new Error(`docker logs failed: ${error.message}`)),
    );
    child.on('close', code => {
      if (code === 0) {
        resolve(password);
      } else {
        reject(new Error(`docker logs failed with exit code ${code}`));
      }
    });
  });

// Read the password the way an operator does on a fresh stack: from the banner
// `flask console bootstrap_admin` prints to the API container log.
const readBootstrapAdminPassword = async () => {
  const filters = [
    '--filter',
    `label=com.docker.compose.service=${API_SERVICE}`,
  ];
  const project = process.env.AI_SHIFU_COMPOSE_PROJECT;
  if (project) {
    filters.push('--filter', `label=com.docker.compose.project=${project}`);
  }
  const containers = runDocker(['ps', '-q', ...filters])
    .split(/\s+/)
    .filter(Boolean);
  if (containers.length !== 1) {
    throw new Error(
      `Expected one running ${API_SERVICE} container, found ` +
        `${containers.length}. Set AI_SHIFU_COMPOSE_PROJECT, or set ` +
        'AI_SHIFU_TEST_ADMIN_PASSWORD to the admin password.',
    );
  }

  const password = await readLoggedPassword(containers[0]);
  if (!password) {
    throw new Error(
      'The API container log has no generated admin password, for example ' +
        'because the container was recreated or BOOTSTRAP_ADMIN_PASSWORD is ' +
        'set. Set AI_SHIFU_TEST_ADMIN_PASSWORD to the admin password.',
    );
  }
  return password;
};

const adminPassword = async () =>
  process.env.AI_SHIFU_TEST_ADMIN_PASSWORD || readBootstrapAdminPassword();

export const callHarnessApi = async <T>(
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

const ensureLoginInputVisible = async (page: Page, selector: string) => {
  const input = page.locator(selector);
  if (await input.isVisible()) {
    return input;
  }

  const tabs = page.getByRole('tab');
  const tabCount = await tabs.count();
  for (let index = 0; index < tabCount; index += 1) {
    await tabs.nth(index).click();
    if (await input.isVisible().catch(() => false)) {
      return input;
    }
  }

  await expect(input).toBeVisible();
  return input;
};

export const loginWithPhone = async (
  page: Page,
  redirectPath: string,
  phone = DEFAULT_PHONE,
) => {
  await page.goto(`/login?redirect=${encodeURIComponent(redirectPath)}`);
  await expect(page.getByTestId('login-page')).toBeVisible();

  const phoneInput = await ensureLoginInputVisible(page, '#phone');
  await phoneInput.fill(phone);

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

// Sign in as the bootstrap admin, the only administrator the stack has.
export const loginAsAdmin = async (page: Page, redirectPath: string) => {
  await page.goto(`/login?redirect=${encodeURIComponent(redirectPath)}`);
  await expect(page.getByTestId('login-page')).toBeVisible();

  const passwordInput = await ensureLoginInputVisible(page, '#password');
  await page.locator('#identifier').fill(ADMIN_USERNAME);
  await passwordInput.fill(await adminPassword());

  const termsCheckbox = page.locator('#terms');
  if (await termsCheckbox.isVisible()) {
    await termsCheckbox.click();
  }

  await passwordInput.press('Enter');
};
