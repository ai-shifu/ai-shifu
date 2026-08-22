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

export const loginWithPhone = async (page: Page, redirectPath: string) => {
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
