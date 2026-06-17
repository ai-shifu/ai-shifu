'use client';

import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';
import { getBoolEnv } from '@/c-utils/envUtils';
import {
  getDynamicApiBaseUrl,
  resolveOfficialSiteUrl,
} from '@/config/environment';

const normalizeStringArray = (value: unknown, fallback: string[]): string[] => {
  if (Array.isArray(value)) {
    return value.filter(item => typeof item === 'string' && item.trim() !== '');
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map(item => item.trim())
      .filter(Boolean);
  }
  return fallback;
};

let initPromise: Promise<void> | null = null;

const resolveRuntimeBase = async (): Promise<string> => {
  const apiBaseUrl = (await getDynamicApiBaseUrl()) || '';
  const normalizedBase = apiBaseUrl.replace(/\/+$/, '');
  return (
    normalizedBase ||
    ((useEnvStore.getState() as EnvStoreState).baseURL || '').replace(
      /\/+$/,
      '',
    ) ||
    ''
  );
};

const buildRuntimeConfigUrl = (resolvedBase: string): string => {
  // Absolute URL: respect whether path already includes /api
  if (resolvedBase.startsWith('http')) {
    try {
      const parsed = new URL(resolvedBase);
      const path = parsed.pathname.replace(/\/+$/, '');
      const endsWithApi = path.endsWith('/api');
      return `${resolvedBase}${
        endsWithApi ? '/runtime-config' : '/api/runtime-config'
      }`;
    } catch {
      // fall through to relative handling
    }
  }

  // Handle empty base - use simple relative path
  if (!resolvedBase) {
    return '/api/runtime-config';
  }

  // Relative URL (e.g. "/api" or "/backend")
  const cleanBase = resolvedBase;
  const endsWithApi =
    cleanBase === '/api' ||
    cleanBase.endsWith('/api') ||
    cleanBase === 'api' ||
    cleanBase.endsWith('api');
  const baseWithLeading = cleanBase.startsWith('/')
    ? cleanBase
    : `/${cleanBase}`;
  return endsWithApi
    ? `${baseWithLeading}/runtime-config`
    : `${baseWithLeading}/api/runtime-config`;
};

const loadRuntimeConfig = async () => {
  const {
    updateAppId,
    updateDefaultLlmModel,
    updateAlwaysShowLessonTree,
    updateUmamiWebsiteId,
    updateUmamiScriptSrc,
    updateEruda,
    updateBaseURL,
    updateLogoWideUrl,
    updateLogoSquareUrl,
    updateFaviconUrl,
    updateEnableWxcode,
    updateHomeUrl,
    updateContactUsUrl,
    updateOfficialSiteUrl,
    updateCurrencySymbol,
    updateBillingEnabled,
    updateStripePublishableKey,
    updateStripeEnabled,
    updatePayOrderExpireSeconds,
    updatePaymentChannels,
    updateLoginMethodsEnabled,
    updateDefaultLoginMethod,
    updateLegalUrls,
    updateCourseId,
  } = useEnvStore.getState() as EnvStoreState;

  const resolvedBase = await resolveRuntimeBase();

  if (resolvedBase) {
    await updateBaseURL(resolvedBase);
  }

  const runtimeUrl = buildRuntimeConfigUrl(resolvedBase);

  const pathShifuBid =
    typeof window !== 'undefined'
      ? (() => {
          try {
            const pathname = window.location.pathname || '';
            const segments = pathname.split('/').filter(Boolean);
            return segments[0] === 'c' && segments[1] ? segments[1] : '';
          } catch {
            return '';
          }
        })()
      : '';

  const runtimeUrlWithShifu = pathShifuBid
    ? `${runtimeUrl}?shifu_bid=${encodeURIComponent(pathShifuBid)}`
    : runtimeUrl;

  const fetchRuntimeConfig = async () => {
    // Always try to fetch backend runtime-config (using absolute or relative URL)
    try {
      const res = await fetch(runtimeUrlWithShifu, { cache: 'no-store' });
      if (res.ok) {
        return res.json();
      }
      console.warn('Backend runtime config fetch failed, status:', res.status);
    } catch (error) {
      console.warn('Backend runtime config fetch error:', error);
    }
    // Fallback to local Next route (still returns base url)
    const fallbackRes = await fetch('/api/config', { cache: 'no-store' });
    if (!fallbackRes.ok) {
      throw new Error(
        `Failed to load runtime config (fallback): ${fallbackRes.status}`,
      );
    }
    return fallbackRes.json();
  };

  const payload = await fetchRuntimeConfig();
  const runtimeConfig = payload?.data ?? payload;
  if (redirectToHomeUrlIfRootPath(runtimeConfig?.homeUrl)) {
    return;
  }

  const paymentChannels = normalizeStringArray(
    runtimeConfig?.paymentChannels,
    (useEnvStore.getState() as EnvStoreState).paymentChannels,
  );
  const loginMethods = normalizeStringArray(
    runtimeConfig?.loginMethodsEnabled,
    (useEnvStore.getState() as EnvStoreState).loginMethodsEnabled,
  );

  /**
   * Course id resolution priority
   *
   * 1. If URL path is /c/<shifu_bid>, keep using the path parameter.
   *    Runtime default course id from backend MUST NOT override it.
   * 2. Otherwise, fall back to backend-provided default course id.
   */
  const hasPathCourseId = !!pathShifuBid;

  if (!hasPathCourseId) {
    // Only apply backend default when there is no explicit course id in the URL path
    await updateCourseId(runtimeConfig?.courseId || '');
  }

  await updateAppId(runtimeConfig?.wechatAppId || '');
  await updateAlwaysShowLessonTree(
    runtimeConfig?.alwaysShowLessonTree?.toString() || 'false',
  );
  await updateUmamiWebsiteId(runtimeConfig?.umamiWebsiteId || '');
  await updateUmamiScriptSrc(runtimeConfig?.umamiScriptSrc || '');
  await updateEruda(runtimeConfig?.enableEruda?.toString() || 'false');
  await updateLogoWideUrl(runtimeConfig?.logoWideUrl || '');
  await updateLogoSquareUrl(runtimeConfig?.logoSquareUrl || '');
  await updateFaviconUrl(runtimeConfig?.faviconUrl || '');
  await updateEnableWxcode(
    runtimeConfig?.enableWechatCode?.toString() || 'true',
  );
  await updateDefaultLlmModel(runtimeConfig?.defaultLlmModel || '');
  await updateHomeUrl(runtimeConfig?.homeUrl || '/');
  await updateContactUsUrl(runtimeConfig?.contactUsUrl || '');
  await updateOfficialSiteUrl(
    resolveOfficialSiteUrl(runtimeConfig?.officialSiteUrl),
  );
  await updateCurrencySymbol(runtimeConfig?.currencySymbol || '¥');
  await updateBillingEnabled(
    runtimeConfig?.billingEnabled !== undefined
      ? runtimeConfig.billingEnabled.toString()
      : 'false',
  );
  await updateStripePublishableKey(runtimeConfig?.stripePublishableKey || '');
  await updateStripeEnabled(
    runtimeConfig?.stripeEnabled !== undefined
      ? runtimeConfig.stripeEnabled.toString()
      : 'false',
  );
  if (
    typeof runtimeConfig?.payOrderExpireSeconds === 'number' &&
    Number.isFinite(runtimeConfig.payOrderExpireSeconds) &&
    runtimeConfig.payOrderExpireSeconds > 0
  ) {
    await updatePayOrderExpireSeconds(runtimeConfig.payOrderExpireSeconds);
  }
  await updatePaymentChannels(paymentChannels);
  await updateLoginMethodsEnabled(loginMethods);
  await updateDefaultLoginMethod(
    typeof runtimeConfig?.defaultLoginMethod === 'string'
      ? runtimeConfig.defaultLoginMethod
      : (useEnvStore.getState() as EnvStoreState).defaultLoginMethod,
  );
  await updateLegalUrls(
    runtimeConfig?.legalUrls ??
      (useEnvStore.getState() as EnvStoreState).legalUrls,
  );
};

export const initializeEnvData = async (): Promise<void> => {
  const { runtimeConfigLoaded } = useEnvStore.getState() as EnvStoreState;
  if (runtimeConfigLoaded) {
    return;
  }

  if (!initPromise) {
    initPromise = (async () => {
      try {
        await loadRuntimeConfig();
      } catch (error) {
        console.error('Failed to initialize runtime environment', error);
      } finally {
        const { setRuntimeConfigLoaded } =
          useEnvStore.getState() as EnvStoreState;
        setRuntimeConfigLoaded(true);
        if (getBoolEnv('eruda')) {
          import('eruda')
            .then(eruda => eruda.default.init())
            .catch(err =>
              console.error('Failed to initialize eruda debugger', err),
            );
        }
      }
    })().finally(() => {
      initPromise = null;
    });
  }

  await initPromise;
};

/**
 * Re-fetch runtime-config for an explicit creator and apply that creator's
 * branding (logo + home url) to the env store. Used by the /admin backend,
 * whose path has no shifu_bid, so the logged-in creator's branding can drive
 * the sidebar logo and its click-through target.
 *
 * Branding fields are applied unconditionally (with sensible fallbacks),
 * mirroring the bootstrap loader, so switching to a creator without custom
 * branding resets to the backend-provided global defaults instead of leaving a
 * previous creator's values behind. Any fetch/parse failure is swallowed.
 */
export const applyCreatorBranding = async (
  creatorBid: string,
): Promise<void> => {
  const normalizedCreatorBid = (creatorBid || '').trim();
  if (!normalizedCreatorBid) {
    return;
  }
  try {
    const resolvedBase = await resolveRuntimeBase();
    const runtimeUrl = buildRuntimeConfigUrl(resolvedBase);
    const url = `${runtimeUrl}?creator_bid=${encodeURIComponent(
      normalizedCreatorBid,
    )}`;
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) {
      return;
    }
    const payload = await res.json();
    const runtimeConfig = payload?.data ?? payload;
    if (!runtimeConfig) {
      return;
    }
    const {
      updateHomeUrl,
      updateLogoWideUrl,
      updateLogoSquareUrl,
      updateFaviconUrl,
    } = useEnvStore.getState() as EnvStoreState;
    await updateHomeUrl(runtimeConfig.homeUrl || '/');
    await updateLogoWideUrl(runtimeConfig.logoWideUrl || '');
    await updateLogoSquareUrl(runtimeConfig.logoSquareUrl || '');
    await updateFaviconUrl(runtimeConfig.faviconUrl || '');
  } catch (error) {
    console.warn('Failed to apply creator branding', error);
  }
};
