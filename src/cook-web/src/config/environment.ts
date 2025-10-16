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

  // WeChat Integration
  wechatAppId: string;
  enableWechatCode: boolean;

  // UI Configuration
  alwaysShowLessonTree: boolean;
  logoHorizontal: string;
  logoVertical: string;

  // Analytics & Tracking
  umamiScriptSrc: string;
  umamiWebsiteId: string;

  // Development & Debugging Tools
  enableEruda: boolean;

  // Authentication Configuration
  loginMethodsEnabled: string[];
  defaultLoginMethod: string;
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
    cachedApiBaseUrl = 'http://localhost:8081';
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
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8081';
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
 * Environment configuration instance with new organized structure
 */
export const environment: EnvironmentConfig = {
  // Core API Configuration
  apiBaseUrl: getApiBaseUrl(),

  // Content & Course Configuration
  courseId: getCourseId(),

  // WeChat Integration
  wechatAppId: getWeChatAppId(),
  enableWechatCode: getWeChatCodeEnabled(),

  // UI Configuration
  alwaysShowLessonTree: getUIAlwaysShowLessonTree(),
  logoHorizontal: getUILogoHorizontal(),
  logoVertical: getUILogoVertical(),

  // Analytics & Tracking
  umamiScriptSrc: getAnalyticsUmamiScript(),
  umamiWebsiteId: getAnalyticsUmamiSiteId(),

  // Development & Debugging Tools
  enableEruda: getDebugErudaEnabled(),

  // Authentication Configuration
  loginMethodsEnabled: getLoginMethodsEnabled(),
  defaultLoginMethod: getDefaultLoginMethod(),
};

export default environment;
