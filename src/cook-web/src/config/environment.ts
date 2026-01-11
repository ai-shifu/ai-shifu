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
  logoWideUrl: string;
  logoSquareUrl: string;
  faviconUrl: string;

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

  // MDF Conversion Configuration
  mdfApiUrl: string;
  mdfApiConfigured: boolean;
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
let configFetched: boolean = false;
let configFetchPromise: Promise<string> | null = null;

const normalizeApiBaseUrl = (value?: string): string => {
  if (!value) return '';
  return value.replace(/\/+$/, '');
};

async function getClientApiBaseUrl(): Promise<string> {
  // Return cached value if already fetched
  if (configFetched) {
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
        cachedApiBaseUrl = normalizeApiBaseUrl(config.apiBaseUrl) || '';
      }
    } catch (error) {
      console.warn('Failed to fetch runtime config:', error);
      cachedApiBaseUrl = '';
    }

    configFetched = true;
    return cachedApiBaseUrl;
  })();

  const result = await configFetchPromise;
  configFetchPromise = null; // Reset after the request completes
  return result;
}

/**
 * Gets the unified API base URL
 * Priority: runtime env > build-time env > empty string
 */
function getApiBaseUrl(): string {
  // 1. Prefer runtime environment variables on the server
  const runtimeApiUrl = normalizeApiBaseUrl(
    getRuntimeEnv('NEXT_PUBLIC_API_BASE_URL'),
  );
  if (runtimeApiUrl) {
    return runtimeApiUrl;
  }

  // 2. Clients fall back to the build value and update dynamically later
  const buildTimeValue = normalizeApiBaseUrl(
    process.env.NEXT_PUBLIC_API_BASE_URL,
  );
  return buildTimeValue || '';
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
  return '';
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
  return '';
}

/**
 * Gets WeChat code enabled status
 */
function getWeChatCodeEnabled(): boolean {
  return true;
}

/**
 * Gets Stripe publishable key
 */
function getStripePublishableKey(): string {
  return '';
}

/**
 * Gets Stripe enable flag
 */
function getStripeEnabled(): boolean {
  return false;
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
  return parsePaymentChannels();
}

/**
 * Gets UI always show lesson tree
 */
function getUIAlwaysShowLessonTree(): boolean {
  return false;
}

/**
 * Gets UI logo horizontal
 */
function getUILogoHorizontal(): string {
  return '';
}

/**
 * Gets UI logo vertical
 */
function getUILogoVertical(): string {
  return '';
}

/**
 * Gets custom wide logo URL (runtime override)
 */
function getLogoWideUrl(): string {
  return getRuntimeEnv('LOGO_WIDE_URL') || process.env.LOGO_WIDE_URL || '';
}

/**
 * Gets custom square logo URL (runtime override)
 */
function getLogoSquareUrl(): string {
  return getRuntimeEnv('LOGO_SQUARE_URL') || process.env.LOGO_SQUARE_URL || '';
}

/**
 * Gets custom favicon URL (runtime override)
 */
function getFaviconUrl(): string {
  return getRuntimeEnv('FAVICON_URL') || process.env.FAVICON_URL || '';
}

/**
 * Gets analytics Umami script
 */
function getAnalyticsUmamiScript(): string {
  return '';
}

/**
 * Gets analytics Umami site ID
 */
function getAnalyticsUmamiSiteId(): string {
  return '';
}

/**
 * Gets debug Eruda enabled
 */
function getDebugErudaEnabled(): boolean {
  return false;
}

/**
 * Gets enabled login methods
 */
function getLoginMethodsEnabled(): string[] {
  return ['phone'];
}

/**
 * Gets default login method
 */
function getDefaultLoginMethod(): string {
  return 'phone';
}

/**
 * Resolve Google OAuth redirect URI.
 * The value always falls back to the canonical callback path so the front end
 * does not need to know the full deployment origin. When necessary, the value
 * can still be overridden with an absolute URL via `NEXT_PUBLIC_GOOGLE_OAUTH_REDIRECT`.
 */
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
 * Gets MDF conversion API URL
 * Returns configured URL or empty string (no fallback)
 */
function getMdfApiUrl(): string {
  return (
    getRuntimeEnv('NEXT_PUBLIC_GEN_MDF_API_URL') ||
    process.env.NEXT_PUBLIC_GEN_MDF_API_URL ||
    ''
  );
}

/**
 * Checks if MDF API is explicitly configured
 * Returns false if URL is empty or not set
 */
function isMdfApiConfigured(): boolean {
  const url =
    getRuntimeEnv('NEXT_PUBLIC_GEN_MDF_API_URL') ||
    process.env.NEXT_PUBLIC_GEN_MDF_API_URL;
  return Boolean(url && url.trim().length > 0);
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
  logoWideUrl: getLogoWideUrl(),
  logoSquareUrl: getLogoSquareUrl(),
  faviconUrl: getFaviconUrl(),

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

  // MDF Conversion Configuration
  mdfApiUrl: getMdfApiUrl(),
  mdfApiConfigured: isMdfApiConfigured(),
};

export default environment;
