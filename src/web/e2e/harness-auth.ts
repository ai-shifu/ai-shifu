import { expect, Page } from '@playwright/test';

const DEFAULT_PHONE = process.env.AI_SHIFU_TEST_PHONE || '13800138000';
const DEFAULT_OTP = process.env.AI_SHIFU_TEST_OTP || '1024';
const DEFAULT_CAPTCHA = process.env.AI_SHIFU_TEST_CAPTCHA || '0000';

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

export const loginWithPhone = async (
  page: Page,
  redirectPath: string,
  phone = DEFAULT_PHONE,
) => {
  await page.goto(`/login?redirect=${encodeURIComponent(redirectPath)}`);
  await expect(page.getByTestId('login-page')).toBeVisible();

  const phoneInput = await ensurePhoneLoginVisible(page);
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

const administratorCredentials = () => {
  const password = process.env.AI_SHIFU_TEST_ADMIN_PASSWORD;
  if (!password) {
    throw new Error(
      'Set AI_SHIFU_TEST_ADMIN_PASSWORD for the isolated runtime harness.',
    );
  }
  return {
    identifier:
      process.env.AI_SHIFU_TEST_ADMIN_IDENTIFIER ||
      'runtime-admin@example.test',
    password,
  };
};

export const initializeAdministrator = async (page: Page) => {
  const statusResponse = await page.request.get('/api/installation/status');
  expect(statusResponse.ok()).toBeTruthy();
  const status = await statusResponse.json();
  expect(status.code).toBe(0);
  if (!status.data.setup_required) {
    // A Playwright retry may follow a committed initialization whose browser
    // session failed. Reuse the same runner-only password, never reopen setup.
    expect(status.data.local_admin_login_enabled).toBe(true);
    await loginWithAdministrator(page);
    return;
  }

  const setupCode = process.env.AI_SHIFU_TEST_SETUP_CODE;
  if (!setupCode) {
    throw new Error(
      'Set AI_SHIFU_TEST_SETUP_CODE from the isolated server console.',
    );
  }
  const { identifier, password } = administratorCredentials();
  await page.goto('/setup');
  await page.locator('#installation-code').fill(setupCode);
  await page.locator('#installation-identifier').fill(identifier);
  await page.locator('#installation-password').fill(password);
  await page.locator('#installation-confirmation').fill(password);
  const initialized = page.waitForResponse(
    response =>
      new URL(response.url()).pathname === '/api/installation/initialize',
  );
  await page.locator('form button[type="submit"]').click();
  expect((await (await initialized).json()).code).toBe(0);
  await page.waitForURL(url => url.pathname === '/admin');
};

export const loginWithAdministrator = async (page: Page) => {
  const { identifier, password } = administratorCredentials();
  await page.goto('/admin-login');
  await page.locator('#installation-identifier').fill(identifier);
  await page.locator('#installation-password').fill(password);
  const authenticated = page.waitForResponse(
    response => new URL(response.url()).pathname === '/api/installation/login',
  );
  await page.locator('form button[type="submit"]').click();
  const payload = await (await authenticated).json();
  expect(payload.code).toBe(0);
  expect(payload.data.userInfo.is_operator).toBeTruthy();
  await page.waitForURL(url => url.pathname === '/admin');
  return payload.data.userInfo.user_id as string;
};

export const verifyStandardPasswordLogin = async (page: Page) => {
  const { identifier, password } = administratorCredentials();
  const response = await page.request.post('/api/user/login_password', {
    data: { identifier, password },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.code).toBe(0);
  expect(payload.data.userInfo.is_operator).toBe(true);
  expect(payload.data.userInfo.has_password).toBe(true);
  expect(payload.data.userInfo.has_local_password).not.toBe(true);
  expect(
    payload.data.userInfo.email || payload.data.userInfo.mobile,
  ).toBeTruthy();
  return payload.data.userInfo.user_id as string;
};
