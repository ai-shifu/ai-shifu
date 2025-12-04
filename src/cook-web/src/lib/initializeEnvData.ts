'use client';

import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';
import { getBoolEnv } from '@/c-utils/envUtils';
import { getDynamicApiBaseUrl } from '@/config/environment';

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

const loadRuntimeConfig = async () => {
  const {
    updateAppId,
    updateDefaultLlmModel,
    updateAlwaysShowLessonTree,
    updateUmamiWebsiteId,
    updateUmamiScriptSrc,
    updateEruda,
    updateBaseURL,
    updateLogoHorizontal,
    updateLogoVertical,
    updateLogoUrl,
    updateEnableWxcode,
    updateHomeUrl,
    updateCurrencySymbol,
    updateStripePublishableKey,
    updateStripeEnabled,
    updatePaymentChannels,
    updateLoginMethodsEnabled,
    updateDefaultLoginMethod,
    updateLegalUrls,
    updateCourseId,
  } = useEnvStore.getState() as EnvStoreState;

  const apiBaseUrl = (await getDynamicApiBaseUrl()) || '';
  const normalizedBase = apiBaseUrl.replace(/\/+$/, '');
  const resolvedBase =
    normalizedBase ||
    ((useEnvStore.getState() as EnvStoreState).baseURL || '').replace(
      /\/+$/,
      '',
    ) ||
    '';

  if (resolvedBase) {
    await updateBaseURL(resolvedBase);
  }

  const buildRuntimeUrl = () => {
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

    // Relative URL (e.g. "/api" or "/backend")
    const cleanBase = resolvedBase || '';
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

  const runtimeUrl = buildRuntimeUrl();

  const fetchRuntimeConfig = async () => {
    // Prefer backend /api/config using discovered apiBaseUrl
    if (apiBaseUrl) {
      const res = await fetch(runtimeUrl, { cache: 'no-store' });
      if (res.ok) {
        return res.json();
      }
      console.warn('Backend runtime config fetch failed, status:', res.status);
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
  const hasPathCourseId =
    typeof window !== 'undefined' &&
    (() => {
      try {
        const pathname = window.location.pathname || '';
        const segments = pathname.split('/').filter(Boolean);
        // Match /c/<shifu_bid> or /c/<shifu_bid>/...
        return segments[0] === 'c' && !!segments[1];
      } catch {
        return false;
      }
    })();

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
  await updateLogoHorizontal(runtimeConfig?.logoHorizontal || '');
  await updateLogoVertical(runtimeConfig?.logoVertical || '');
  await updateLogoUrl(runtimeConfig?.logoUrl || '');
  await updateEnableWxcode(
    runtimeConfig?.enableWechatCode?.toString() || 'true',
  );
  await updateDefaultLlmModel(runtimeConfig?.defaultLlmModel || '');
  await updateHomeUrl(runtimeConfig?.homeUrl || '');
  await updateCurrencySymbol(runtimeConfig?.currencySymbol || '¥');
  await updateStripePublishableKey(runtimeConfig?.stripePublishableKey || '');
  await updateStripeEnabled(
    runtimeConfig?.stripeEnabled !== undefined
      ? runtimeConfig.stripeEnabled.toString()
      : 'false',
  );
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
