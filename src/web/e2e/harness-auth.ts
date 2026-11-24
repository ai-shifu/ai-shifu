import { expect, Page } from '@playwright/test';

const DEFAULT_PHONE = process.env.AI_SHIFU_TEST_PHONE || '13800138000';
const DEFAULT_OTP = process.env.AI_SHIFU_TEST_OTP || '1024';
const DEFAULT_CAPTCHA = process.env.AI_SHIFU_TEST_CAPTCHA || '0000';
// Matches BOOTSTRAP_ADMIN_PASSWORD in docker/docker-compose.runtime-harness.yml.
const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD =
  process.env.AI_SHIFU_TEST_ADMIN_PASSWORD || 'RuntimeHarness1Admin';

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
  await passwordInput.fill(ADMIN_PASSWORD);

  const termsCheckbox = page.locator('#terms');
  if (await termsCheckbox.isVisible()) {
    await termsCheckbox.click();
  }

  await passwordInput.press('Enter');
};
