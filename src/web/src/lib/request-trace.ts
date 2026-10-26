import { v4 as uuidv4 } from 'uuid';

export const TRACE_REQUEST_ID_HEADER = 'X-Request-ID';
export const TRACE_HARNESS_RUN_ID_HEADER = 'X-Harness-Run-ID';

declare global {
  interface Window {
    __HARNESS_RUN_ID__?: string;
  }
}

export type TraceHeaderResult = {
  headers: Record<string, string>;
  requestId: string;
  harnessRunId?: string;
};

export type ResponseTraceHeaders = {
  requestId?: string;
  harnessRunId?: string;
};

export const createRequestId = () => uuidv4().replace(/-/g, '');

const normalizeHeaderName = (name: string) => name.toLowerCase();

export const headersToRecord = (
  headers?: HeadersInit,
): Record<string, string> => {
  const record: Record<string, string> = {};
  if (!headers) {
    return record;
  }

  if (typeof Headers !== 'undefined' && headers instanceof Headers) {
    headers.forEach((value, key) => {
      record[key] = value;
    });
    return record;
  }

  if (Array.isArray(headers)) {
    headers.forEach(([key, value]) => {
      record[key] = String(value);
    });
    return record;
  }

  Object.entries(headers).forEach(([key, value]) => {
    if (value !== undefined) {
      record[key] = String(value);
    }
  });
  return record;
};

const findHeaderKey = (headers: Record<string, string>, name: string) => {
  const normalizedName = normalizeHeaderName(name);
  return Object.keys(headers).find(
    key => normalizeHeaderName(key) === normalizedName,
  );
};

const getHeaderValue = (headers: Record<string, string>, name: string) => {
  const key = findHeaderKey(headers, name);
  return key ? String(headers[key] || '').trim() : '';
};

const setHeaderValue = (
  headers: Record<string, string>,
  name: string,
  value: string,
) => {
  const key = findHeaderKey(headers, name) || name;
  headers[key] = value;
};

const getStorageValue = (storage: Storage | undefined, key: string) => {
  try {
    return String(storage?.getItem(key) || '').trim();
  } catch {
    return '';
  }
};

export const getHarnessRunId = () => {
  const envValue =
    process.env.NEXT_PUBLIC_HARNESS_RUN_ID ||
    process.env.NEXT_PUBLIC_AI_SHIFU_HARNESS_RUN_ID ||
    '';

  if (typeof window === 'undefined') {
    return String(envValue || '').trim();
  }

  return (
    String(window.__HARNESS_RUN_ID__ || '').trim() ||
    getStorageValue(window.sessionStorage, 'harness_run_id') ||
    getStorageValue(window.sessionStorage, 'HARNESS_RUN_ID') ||
    getStorageValue(window.localStorage, 'harness_run_id') ||
    getStorageValue(window.localStorage, 'HARNESS_RUN_ID') ||
    String(envValue || '').trim()
  );
};

export const buildTraceHeaders = (
  headers?: HeadersInit,
  fallbackRequestId = createRequestId,
): TraceHeaderResult => {
  const mergedHeaders = headersToRecord(headers);
  const requestId =
    getHeaderValue(mergedHeaders, TRACE_REQUEST_ID_HEADER) ||
    fallbackRequestId();
  const harnessRunId =
    getHeaderValue(mergedHeaders, TRACE_HARNESS_RUN_ID_HEADER) ||
    getHarnessRunId();

  setHeaderValue(mergedHeaders, TRACE_REQUEST_ID_HEADER, requestId);
  if (harnessRunId) {
    setHeaderValue(mergedHeaders, TRACE_HARNESS_RUN_ID_HEADER, harnessRunId);
  }

  return {
    headers: mergedHeaders,
    requestId,
    harnessRunId: harnessRunId || undefined,
  };
};

export const readTraceHeadersFromResponse = (
  response?: Response | null,
): ResponseTraceHeaders => {
  if (!response?.headers) {
    return {};
  }

  return {
    requestId: response.headers.get(TRACE_REQUEST_ID_HEADER) || undefined,
    harnessRunId:
      response.headers.get(TRACE_HARNESS_RUN_ID_HEADER) || undefined,
  };
};
