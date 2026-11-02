'use client';

import { useEnvStore } from '@/store/env-store';
import { EnvStoreState } from '@/types/store';
import { getBoolEnv } from '@/lib/env-utils';
import {
  environment,
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

let activeCourseBid: string | null = null;
let loadedCourseBid: string | null = null;
let paymentSettingsCourseBid: string | null = null;
let activeLoad: Promise<void> | null = null;
let generation = 0;
let erudaStarted = false;
let siteLogos = {
  logoWideUrl: environment.logoWideUrl,
  logoSquareUrl: environment.logoSquareUrl,
};

const getCourseBid = (pathname: string): string => {
  const segments = pathname.split('/').filter(Boolean);
  return segments[0] === 'c' && segments[1] ? segments[1] : '';
};

const resolveRuntimeBase = async (): Promise<string> => {
  const apiBaseUrl = (await getDynamicApiBaseUrl()) || '';
  // An empty dynamic base intentionally selects the current site's /api.
  // Falling back to the build-time origin would lose a custom domain's host.
  return apiBaseUrl.replace(/\/+$/, '');
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

const loadRuntimeConfig = async (courseBid: string, resolvedBase: string) => {
  const runtimeUrl = buildRuntimeConfigUrl(resolvedBase);
  const runtimeUrlWithShifu = courseBid
    ? `${runtimeUrl}?shifu_bid=${encodeURIComponent(courseBid)}`
    : runtimeUrl;
  const response = await fetch(runtimeUrlWithShifu, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`Backend runtime config fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  if (payload?.code !== undefined && payload.code !== 0) {
    throw new Error('Backend runtime config rejected the requested context');
  }
  const runtimeConfig = payload?.data ?? payload;
  if (
    !runtimeConfig ||
    typeof runtimeConfig !== 'object' ||
    Array.isArray(runtimeConfig) ||
    typeof runtimeConfig.logoWideUrl !== 'string' ||
    typeof runtimeConfig.logoSquareUrl !== 'string'
  ) {
    throw new Error('Backend runtime config returned an invalid payload');
  }
  return { runtimeConfig, resolvedBase };
};

const pendingLoads = new Map<string, ReturnType<typeof loadRuntimeConfig>>();

const getRuntimeConfig = (courseBid: string, resolvedBase: string) => {
  const pending = pendingLoads.get(courseBid);
  if (pending) return pending;
  const loading = loadRuntimeConfig(courseBid, resolvedBase).finally(() => {
    pendingLoads.delete(courseBid);
  });
  pendingLoads.set(courseBid, loading);
  return loading;
};

const applyRuntimeConfig = (
  {
    runtimeConfig,
    resolvedBase,
  }: Awaited<ReturnType<typeof loadRuntimeConfig>>,
  courseBid: string,
  requestGeneration: number,
) => {
  const current = useEnvStore.getState();
  const paymentChannels = normalizeStringArray(
    runtimeConfig?.paymentChannels,
    current.paymentChannels,
  );
  const loginMethods = normalizeStringArray(
    runtimeConfig?.loginMethodsEnabled,
    current.loginMethodsEnabled,
  );
  const next: Partial<EnvStoreState> = {
    baseURL: resolvedBase,
    appId: runtimeConfig?.wechatAppId || '',
    alwaysShowLessonTree:
      runtimeConfig?.alwaysShowLessonTree?.toString() || 'false',
    umamiWebsiteId: runtimeConfig?.umamiWebsiteId || '',
    umamiScriptSrc: runtimeConfig?.umamiScriptSrc || '',
    eruda: runtimeConfig?.enableEruda?.toString() || 'false',
    logoWideUrl: runtimeConfig?.logoWideUrl || '',
    logoSquareUrl: runtimeConfig?.logoSquareUrl || '',
    faviconUrl: runtimeConfig?.faviconUrl || '',
    enableWxcode: runtimeConfig?.enableWechatCode?.toString() || 'true',
    homeUrl: runtimeConfig?.homeUrl || environment.homeUrl,
    contactUsUrl: runtimeConfig?.contactUsUrl || '',
    officialSiteUrl: resolveOfficialSiteUrl(runtimeConfig?.officialSiteUrl),
    currencySymbol: runtimeConfig?.currencySymbol || '¥',
    defaultCoursePrice:
      typeof runtimeConfig?.defaultCoursePrice === 'number'
        ? runtimeConfig.defaultCoursePrice
        : 0.5,
    minimumPaidCoursePrice:
      typeof runtimeConfig?.minimumPaidCoursePrice === 'number'
        ? runtimeConfig.minimumPaidCoursePrice
        : 0.5,
    billingEnabled:
      runtimeConfig?.billingEnabled !== undefined
        ? runtimeConfig.billingEnabled.toString()
        : 'false',
    stripePublishableKey: runtimeConfig?.stripePublishableKey || '',
    stripeEnabled:
      runtimeConfig?.stripeEnabled !== undefined
        ? runtimeConfig.stripeEnabled.toString()
        : 'false',
    paymentChannels,
    loginMethodsEnabled: loginMethods,
    defaultLoginMethod:
      typeof runtimeConfig?.defaultLoginMethod === 'string'
        ? runtimeConfig.defaultLoginMethod
        : current.defaultLoginMethod,
    legalUrls: runtimeConfig?.legalUrls ?? current.legalUrls,
    runtimeConfigLoaded: true,
    runtimeConfigContext: {
      courseId: courseBid,
      status: 'ready',
      generation: requestGeneration,
    },
  };
  if (
    typeof runtimeConfig?.payOrderExpireSeconds === 'number' &&
    Number.isFinite(runtimeConfig.payOrderExpireSeconds) &&
    runtimeConfig.payOrderExpireSeconds > 0
  ) {
    next.payOrderExpireSeconds = runtimeConfig.payOrderExpireSeconds;
  }
  if (!courseBid || runtimeConfig?.domain?.is_custom_domain) {
    siteLogos = {
      logoWideUrl: next.logoWideUrl || '',
      logoSquareUrl: next.logoSquareUrl || '',
    };
  }
  // Store setters only call Zustand set. One commit keeps route generations
  // from interleaving branding, authentication and payment fields.
  paymentSettingsCourseBid = courseBid;
  useEnvStore.setState(next);
};

export const initializeEnvData = async (pathname?: string): Promise<void> => {
  const courseBid = getCourseBid(
    pathname ?? (typeof window === 'undefined' ? '' : window.location.pathname),
  );
  if (courseBid === activeCourseBid) {
    if (activeLoad) return activeLoad;
    if (loadedCourseBid === courseBid) return;
  }
  activeCourseBid = courseBid;
  const requestGeneration = ++generation;
  const current = useEnvStore.getState();
  const verifiedStoreContext =
    current.runtimeConfigContext?.status === 'ready'
      ? current.runtimeConfigContext.courseId
      : null;
  const previousPaymentContext =
    paymentSettingsCourseBid ?? verifiedStoreContext;
  const hasCurrentPaymentSettings =
    current.runtimeConfigLoaded && previousPaymentContext === courseBid;
  paymentSettingsCourseBid = hasCurrentPaymentSettings ? courseBid : null;
  useEnvStore.setState({
    ...siteLogos,
    // Pending or failed configuration cannot borrow another context's merchant.
    // Keep a known configuration only when refreshing that same context.
    ...(!hasCurrentPaymentSettings && {
      billingEnabled: 'false',
      stripeEnabled: 'false',
      stripePublishableKey: '',
      paymentChannels: [],
    }),
    runtimeConfigContext: {
      courseId: courseBid,
      status: 'loading',
      generation: requestGeneration,
    },
  });
  const loading = (async () => {
    try {
      const resolvedBase = await resolveRuntimeBase();
      if (generation !== requestGeneration) return;
      // Discovery owns transport configuration even if runtime settings fail.
      useEnvStore.setState({ baseURL: resolvedBase });
      const result = await getRuntimeConfig(courseBid, resolvedBase);
      if (generation !== requestGeneration) return;
      applyRuntimeConfig(result, courseBid, requestGeneration);
      loadedCourseBid = courseBid;
      if (getBoolEnv('eruda') && !erudaStarted) {
        erudaStarted = true;
        import('eruda')
          .then(eruda => eruda.default.init())
          .catch(err => {
            erudaStarted = false;
            console.error('Failed to initialize eruda debugger', err);
          });
      }
    } catch (error) {
      if (generation !== requestGeneration) return;
      loadedCourseBid = null;
      console.error('Failed to initialize runtime environment', error);
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        runtimeConfigContext: {
          courseId: courseBid,
          status: 'failed',
          generation: requestGeneration,
        },
      });
    } finally {
      if (generation === requestGeneration) activeLoad = null;
    }
  })();
  activeLoad = loading;
  await loading;
};
