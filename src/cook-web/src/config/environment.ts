/**
 * Centralized Environment Variable Management
 *
 * This module provides a unified interface for accessing all environment variables
 * across the application. It uses the new standardized naming scheme.
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
 * Gets the unified API base URL
 */
function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8081';
}

/**
 * Gets course ID
 */
function getCourseId(): string {
  return process.env.NEXT_PUBLIC_DEFAULT_COURSE_ID || '';
}

/**
 * Gets WeChat App ID
 */
function getWeChatAppId(): string {
  return process.env.NEXT_PUBLIC_WECHAT_APP_ID || '';
}

/**
 * Gets WeChat code enabled status
 */
function getWeChatCodeEnabled(): boolean {
  const value = process.env.NEXT_PUBLIC_WECHAT_CODE_ENABLED;
  return getBooleanValue(value, true);
}

/**
 * Gets UI always show lesson tree
 */
function getUIAlwaysShowLessonTree(): boolean {
  const value = process.env.NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE;
  return getBooleanValue(value, false);
}

/**
 * Gets UI logo horizontal
 */
function getUILogoHorizontal(): string {
  return process.env.NEXT_PUBLIC_UI_LOGO_HORIZONTAL || '';
}

/**
 * Gets UI logo vertical
 */
function getUILogoVertical(): string {
  return process.env.NEXT_PUBLIC_UI_LOGO_VERTICAL || '';
}

/**
 * Gets analytics Umami script
 */
function getAnalyticsUmamiScript(): string {
  return process.env.NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT || '';
}

/**
 * Gets analytics Umami site ID
 */
function getAnalyticsUmamiSiteId(): string {
  return process.env.NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID || '';
}

/**
 * Gets debug Eruda enabled
 */
function getDebugErudaEnabled(): boolean {
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
