'use client';

import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';
import { getBoolEnv } from '@/c-utils/envUtils';

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
  } = useEnvStore.getState() as EnvStoreState;

  const res = await fetch('/api/config', {
    method: 'GET',
    referrer: 'no-referrer',
  });

  if (!res.ok) {
    return;
  }

  const data = await res.json();
  if (redirectToHomeUrlIfRootPath(data?.homeUrl)) {
    return;
  }

  // await updateCourseId(data?.courseId || '');
  await updateAppId(data?.wechatAppId || '');
  await updateAlwaysShowLessonTree(data?.alwaysShowLessonTree || 'false');
  await updateUmamiWebsiteId(data?.umamiWebsiteId || '');
  await updateUmamiScriptSrc(data?.umamiScriptSrc || '');
  await updateEruda(data?.enableEruda || 'false');
  await updateBaseURL(data?.apiBaseUrl || '');
  await updateLogoHorizontal(data?.logoHorizontal || '');
  await updateLogoVertical(data?.logoVertical || '');
  await updateLogoUrl(data?.logoUrl || '');
  await updateEnableWxcode(data?.enableWechatCode?.toString() || 'true');
  await updateDefaultLlmModel(data?.defaultLlmModel || '');
  await updateHomeUrl(data?.homeUrl || '');
  await updateCurrencySymbol(data?.currencySymbol || '¥');
  await updateStripePublishableKey(data?.stripePublishableKey || '');
  await updateStripeEnabled(
    data?.stripeEnabled !== undefined
      ? data.stripeEnabled.toString()
      : 'false',
  );
  await updatePaymentChannels(
    Array.isArray(data?.paymentChannels) && data.paymentChannels.length > 0
      ? data.paymentChannels
      : (useEnvStore.getState() as EnvStoreState).paymentChannels,
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
