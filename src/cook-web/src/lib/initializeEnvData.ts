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
  } = useEnvStore.getState() as EnvStoreState;

  const apiBaseUrl = (await getDynamicApiBaseUrl()) || '';
  const runtimeUrl = `${apiBaseUrl.replace(/\/$/, '')}/api/config`;

  const res = await fetch(runtimeUrl, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to load runtime config: ${res.status}`);
  }
  const payload = await res.json();
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

  // await updateCourseId(data?.courseId || '');
  await updateAppId(runtimeConfig?.wechatAppId || '');
  await updateAlwaysShowLessonTree(
    runtimeConfig?.alwaysShowLessonTree?.toString() || 'false',
  );
  await updateUmamiWebsiteId(runtimeConfig?.umamiWebsiteId || '');
  await updateUmamiScriptSrc(runtimeConfig?.umamiScriptSrc || '');
  await updateEruda(runtimeConfig?.enableEruda?.toString() || 'false');
  await updateBaseURL(runtimeConfig?.apiBaseUrl || '');
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
