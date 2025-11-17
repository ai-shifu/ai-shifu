/**
 * Centralized Environment Variable Management
 *
 * This module provides a unified interface for accessing all environment variables
 * across the application. It uses the new standardized naming scheme.
 *
 * Supports retrieving environment variables at runtime
 */

interface EnvironmentConfig {
  // Core API Configuration
  apiBaseUrl: string;

  // Content & Course Configuration
  courseId: string;
  defaultLlmModel: string;
  currencySymbol: string;

  // WeChat Integration
  wechatAppId: string;
  enableWechatCode: boolean;

  // Payment Configuration
  stripePublishableKey: string;
  stripeEnabled: boolean;
  paymentChannels: string[];

  // UI Configuration
  alwaysShowLessonTree: boolean;
  logoHorizontal: string;
  logoVertical: string;
  logoUrl: string;

  // Analytics & Tracking
  umamiScriptSrc: string;
  umamiWebsiteId: string;

  // Development & Debugging Tools
  enableEruda: boolean;

  // Authentication Configuration
  loginMethodsEnabled: string[];
  defaultLoginMethod: string;

  // Redirect Configuration
  homeUrl: string;

  // Legal Documents Configuration
  legalUrls: {
    agreement: {
      'zh-CN': string;
      'en-US': string;
    };
    privacy: {
      'zh-CN': string;
      'en-US': string;
    };
  };
}

/**
 * Runtime helper for reading environment variables
 * Executed on the server during SSR
 */
function getRuntimeEnv(key: string): string | undefined {
  if (typeof window === 'undefined') {
    // Server-side
    return process.env[key];
  }
  return undefined;
}

/**
 * Client-side retrieval for the API base URL
 * Fetches /api/config at runtime so npm start can pick up env overrides
 */
let cachedApiBaseUrl: string = '';
let configFetchPromise: Promise<string> | null = null;

async function getClientApiBaseUrl(): Promise<string> {
  if (cachedApiBaseUrl && cachedApiBaseUrl !== '') {
    return cachedApiBaseUrl;
  }

  // Prevent concurrent fetches
  if (configFetchPromise) {
    return configFetchPromise;
  }

  configFetchPromise = (async () => {
    try {
      const response = await fetch('/api/config');
      if (response.ok) {
        const config = await response.json();
        if (config.apiBaseUrl) {
          cachedApiBaseUrl = config.apiBaseUrl;
          return cachedApiBaseUrl;
        }
      }
    } catch (error) {
      console.warn('Failed to fetch runtime config:', error);
    }

    // Fallback to the default value when fetching fails
    cachedApiBaseUrl = 'http://localhost:8080';
    return cachedApiBaseUrl;
  })();

  const result = await configFetchPromise;
  configFetchPromise = null; // Reset after the request completes
  return result;
}

/**
 * Gets the unified API base URL
 * Priority: runtime env > build-time env > default
 */
function getApiBaseUrl(): string {
  // 1. Prefer runtime environment variables on the server
  const runtimeApiUrl = getRuntimeEnv('NEXT_PUBLIC_API_BASE_URL');
  if (runtimeApiUrl) {
    return runtimeApiUrl;
  }

  // 2. Clients fall back to the build value and update dynamically later
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';
}

/**
 * Gets the dynamic API base URL (client-side)
 */
export async function getDynamicApiBaseUrl(): Promise<string> {
  if (typeof window === 'undefined') {
    // Server can return immediately
    return getApiBaseUrl();
  } else {
    // Client fetches it dynamically
    return getClientApiBaseUrl();
  }
}

/**
 * Gets course ID
 */
function getCourseId(): string {
  const runtimeCourseId = getRuntimeEnv('NEXT_PUBLIC_DEFAULT_COURSE_ID');
  if (runtimeCourseId) {
    return runtimeCourseId;
  }
  return process.env.NEXT_PUBLIC_DEFAULT_COURSE_ID || '';
}

/**
 * Gets default LLM model
 */
function getDefaultLlmModel(): string {
  return (
    getRuntimeEnv('DEFAULT_LLM_MODEL') || process.env.DEFAULT_LLM_MODEL || ''
  );
}

/**
 * Gets WeChat App ID
 */
function getWeChatAppId(): string {
  const runtimeAppId = getRuntimeEnv('NEXT_PUBLIC_WECHAT_APP_ID');
  if (runtimeAppId) {
    return runtimeAppId;
  }
  return process.env.NEXT_PUBLIC_WECHAT_APP_ID || '';
}

/**
 * Gets WeChat code enabled status
 */
function getWeChatCodeEnabled(): boolean {
  const runtimeEnabled = getRuntimeEnv('NEXT_PUBLIC_WECHAT_CODE_ENABLED');
  if (runtimeEnabled !== undefined) {
    return getBooleanValue(runtimeEnabled, true);
  }
  const value = process.env.NEXT_PUBLIC_WECHAT_CODE_ENABLED;
  return getBooleanValue(value, true);
}

/**
 * Gets Stripe publishable key
 */
function getStripePublishableKey(): string {
  const runtimeKey = getRuntimeEnv('NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY');
  if (runtimeKey) {
    return runtimeKey;
  }
  return process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || '';
}

/**
 * Gets Stripe enable flag
 */
function getStripeEnabled(): boolean {
  const runtimeEnabled = getRuntimeEnv('NEXT_PUBLIC_STRIPE_ENABLED');
  if (runtimeEnabled !== undefined) {
    return getBooleanValue(runtimeEnabled, false);
  }
  const value = process.env.NEXT_PUBLIC_STRIPE_ENABLED;
  return getBooleanValue(value, false);
}

function parsePaymentChannels(value?: string): string[] {
  if (!value) return ['pingxx', 'stripe'];
  const channels = value
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(Boolean);
  return channels.length > 0 ? channels : ['pingxx', 'stripe'];
}

function getPaymentChannels(): string[] {
  const runtime =
    getRuntimeEnv('PAYMENT_CHANNELS_ENABLED') ||
    getRuntimeEnv('NEXT_PUBLIC_PAYMENT_CHANNELS_ENABLED');
  if (runtime) {
    return parsePaymentChannels(runtime);
  }
  const buildValue =
    process.env.PAYMENT_CHANNELS_ENABLED ||
    process.env.NEXT_PUBLIC_PAYMENT_CHANNELS_ENABLED;
  return parsePaymentChannels(buildValue);
}

/**
 * Gets UI always show lesson tree
 */
function getUIAlwaysShowLessonTree(): boolean {
  const runtimeValue = getRuntimeEnv('NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE');
  if (runtimeValue !== undefined) {
    return getBooleanValue(runtimeValue, false);
  }
  const value = process.env.NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE;
  return getBooleanValue(value, false);
}

/**
 * Gets UI logo horizontal
 */
function getUILogoHorizontal(): string {
  const runtimeLogo = getRuntimeEnv('NEXT_PUBLIC_UI_LOGO_HORIZONTAL');
  if (runtimeLogo) {
    return runtimeLogo;
  }
  return process.env.NEXT_PUBLIC_UI_LOGO_HORIZONTAL || '';
}

/**
 * Gets UI logo vertical
 */
function getUILogoVertical(): string {
  const runtimeLogo = getRuntimeEnv('NEXT_PUBLIC_UI_LOGO_VERTICAL');
  if (runtimeLogo) {
    return runtimeLogo;
  }
  return process.env.NEXT_PUBLIC_UI_LOGO_VERTICAL || '';
}

/**
 * Gets custom logo URL (runtime override)
 */
function getLogoUrl(): string {
  return getRuntimeEnv('LOGO_URL') || process.env.LOGO_URL || '';
}

/**
 * Gets analytics Umami script
 */
function getAnalyticsUmamiScript(): string {
  const runtimeScript = getRuntimeEnv('NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT');
  if (runtimeScript) {
    return runtimeScript;
  }
  return process.env.NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT || '';
}

/**
 * Gets analytics Umami site ID
 */
function getAnalyticsUmamiSiteId(): string {
  const runtimeSiteId = getRuntimeEnv('NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID');
  if (runtimeSiteId) {
    return runtimeSiteId;
  }
  return process.env.NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID || '';
}

/**
 * Gets debug Eruda enabled
 */
function getDebugErudaEnabled(): boolean {
  const runtimeEruda = getRuntimeEnv('NEXT_PUBLIC_DEBUG_ERUDA_ENABLED');
  if (runtimeEruda !== undefined) {
    return getBooleanValue(runtimeEruda, false);
  }
  const value = process.env.NEXT_PUBLIC_DEBUG_ERUDA_ENABLED;
  return getBooleanValue(value, false);
}

/**
 * Gets enabled login methods
 */
function getLoginMethodsEnabled(): string[] {
  const runtimeMethods = getRuntimeEnv('NEXT_PUBLIC_LOGIN_METHODS_ENABLED');
  if (runtimeMethods) {
    const methods = runtimeMethods
      .split(',')
      .map(method => method.trim())
      .filter(Boolean);
    return methods.length > 0 ? methods : ['phone'];
  }

  const value = process.env.NEXT_PUBLIC_LOGIN_METHODS_ENABLED || 'phone';
  const methods = value
    .split(',')
    .map(method => method.trim())
    .filter(Boolean);
  return methods.length > 0 ? methods : ['phone'];
}

/**
 * Gets default login method
 */
function getDefaultLoginMethod(): string {
  return (
    getRuntimeEnv('NEXT_PUBLIC_DEFAULT_LOGIN_METHOD') ||
    process.env.NEXT_PUBLIC_DEFAULT_LOGIN_METHOD ||
    'phone'
  );
}

/**
 * Resolve Google OAuth redirect URI.
 * The value always falls back to the canonical callback path so the front end
 * does not need to know the full deployment origin. When necessary, the value
 * can still be overridden with an absolute URL via `NEXT_PUBLIC_GOOGLE_OAUTH_REDIRECT`.
 */
/**
 * Converts string boolean values to actual booleans
 */
function getBooleanValue(
  value: string | undefined,
  defaultValue: boolean = false,
): boolean {
  if (value === undefined) return defaultValue;
  return value.toLowerCase() === 'true';
}

/**
 * Gets home URL
 */
function getHomeUrl(): string {
  return getRuntimeEnv('HOME_URL') || process.env.HOME_URL || '/admin';
}

/**
 * Gets currency symbol
 */
function getCurrencySymbol(): string {
  return getRuntimeEnv('CURRENCY_SYMBOL') || process.env.CURRENCY_SYMBOL || '¥';
}

/**
 * Gets legal document URLs for all supported languages
 */
function getLegalUrls(): {
  agreement: { 'zh-CN': string; 'en-US': string };
  privacy: { 'zh-CN': string; 'en-US': string };
} {
  return {
    agreement: {
      'zh-CN':
        getRuntimeEnv('LEGAL_AGREEMENT_URL_ZH_CN') ||
        process.env.LEGAL_AGREEMENT_URL_ZH_CN ||
        '',
      'en-US':
        getRuntimeEnv('LEGAL_AGREEMENT_URL_EN_US') ||
        process.env.LEGAL_AGREEMENT_URL_EN_US ||
        '',
    },
    privacy: {
      'zh-CN':
        getRuntimeEnv('LEGAL_PRIVACY_URL_ZH_CN') ||
        process.env.LEGAL_PRIVACY_URL_ZH_CN ||
        '',
      'en-US':
        getRuntimeEnv('LEGAL_PRIVACY_URL_EN_US') ||
        process.env.LEGAL_PRIVACY_URL_EN_US ||
        '',
    },
  };
}

/**
 * Environment configuration instance with new organized structure
 */
export const environment: EnvironmentConfig = {
  // Core API Configuration
  apiBaseUrl: getApiBaseUrl(),

  // Content & Course Configuration
  courseId: getCourseId(),
  defaultLlmModel: getDefaultLlmModel(),

  // WeChat Integration
  wechatAppId: getWeChatAppId(),
  enableWechatCode: getWeChatCodeEnabled(),

  // Payment Configuration
  stripePublishableKey: getStripePublishableKey(),
  stripeEnabled: getStripeEnabled(),
  paymentChannels: getPaymentChannels(),

  // UI Configuration
  alwaysShowLessonTree: getUIAlwaysShowLessonTree(),
  logoHorizontal: getUILogoHorizontal(),
  logoVertical: getUILogoVertical(),
  logoUrl: getLogoUrl(),

  // Analytics & Tracking
  umamiScriptSrc: getAnalyticsUmamiScript(),
  umamiWebsiteId: getAnalyticsUmamiSiteId(),

  // Development & Debugging Tools
  enableEruda: getDebugErudaEnabled(),

  // Authentication Configuration
  loginMethodsEnabled: getLoginMethodsEnabled(),
  defaultLoginMethod: getDefaultLoginMethod(),

  // Redirect Configuration
  homeUrl: getHomeUrl(),
  currencySymbol: getCurrencySymbol(),

  // Legal Documents Configuration
  legalUrls: getLegalUrls(),
};

export default environment;
