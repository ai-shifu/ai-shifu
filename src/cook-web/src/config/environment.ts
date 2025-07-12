/**
 * Centralized Environment Variable Management
 *
 * This module provides a unified interface for accessing all environment variables
 * across the application. It uses the new standardized naming scheme.
 *
 * 支持运行时动态获取环境变量
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
}

/**
 * 运行时获取环境变量
 * 在服务端运行时获取环境变量
 */
function getRuntimeEnv(key: string): string | undefined {
  if (typeof window === 'undefined') {
    // 服务端
    return process.env[key];
  }
  return undefined;
}

/**
 * Gets the unified API base URL
 * 优先级：运行时环境变量 > 构建时环境变量 > 默认值
 */
function getApiBaseUrl(): string {
  // 1. 优先使用运行时环境变量
  const runtimeApiUrl = getRuntimeEnv('NEXT_PUBLIC_API_BASE_URL');
  if (runtimeApiUrl) {
    return runtimeApiUrl;
  }

  // 2. 使用构建时环境变量
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8081';
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
 * Converts string boolean values to actual booleans
 */
function getBooleanValue(value: string | undefined, defaultValue: boolean = false): boolean {
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
};

export default environment;
