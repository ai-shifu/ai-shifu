import { useUserStore } from '@/store';
import { getStringEnv } from '@/c-utils/envUtils';
import { getDynamicApiBaseUrl } from '@/config/environment';
import { toast } from '@/hooks/useToast';
import i18n from 'i18next';
import { v4 as uuidv4 } from 'uuid';

const AUTH_ERROR_CODES = new Set([1001, 1004, 1005]);
let isHandlingAuthError = false;

// ===== Type Definitions =====
export type RequestConfig = RequestInit & { params?: any; data?: any };

export type StreamRequestConfig = RequestInit & {
  params?: any;
  data?: any;
  parseChunk?: (chunkValue: string) => string;
};
export type StreamCallback = (
  done: boolean,
  text: string,
  abort: () => void,
) => void;

// ===== Error Handling =====
export class ErrorWithCode extends Error {
  code: number;
  constructor(message: string, code: number) {
    super(message);
    this.code = code;
  }
}

// Unified error handling function
const handleApiError = (error: ErrorWithCode, showToast = true) => {
  if (showToast) {
    toast({
      title: error.message || i18n.t('common.core.networkError'),
      variant: 'destructive',
    });
  }

  // Dispatch error event (only on client side)
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const apiError = new CustomEvent('apiError', {
      detail: error,
      bubbles: true,
    });
    document.dispatchEvent(apiError);
  }
};

const handleAuthRecovery = async () => {
  if (
    isHandlingAuthError ||
    typeof window === 'undefined' ||
    (window as any).__IS_LOGGING_OUT__
  ) {
    return;
  }

  const { logout } = useUserStore.getState();
  if (!logout) {
    return;
  }

  isHandlingAuthError = true;
  try {
    await logout(false);
  } catch (authError) {
    console.warn('Failed to recover from auth error:', authError);
  } finally {
    isHandlingAuthError = false;
  }
};

// Check response status code and handle business logic
const handleBusinessCode = async (
  response: { code: number; message?: string; data?: unknown },
  requestToken?: string,
) => {
  const error = new ErrorWithCode(
    response.message || i18n.t('common.core.unknownError'),
    response.code || -1,
  );

  const isAuthError = AUTH_ERROR_CODES.has(response.code);
  const currentToken = useUserStore.getState().getToken?.();
  const tokenChangedDuringRequest =
    isAuthError && currentToken && requestToken !== currentToken;

  if (response.code !== 0) {
    // Special status codes do not show toast
    if (!isAuthError) {
      handleApiError(error);
    }

    // If the token has changed since this request was sent, treat the auth error
    // as stale and avoid logging the user out with a newer session active.
    if (tokenChangedDuringRequest) {
      return Promise.reject(error);
    }

    if (isAuthError) {
      await handleAuthRecovery();
    }

    // Authentication related errors, redirect to login (only on client side)
    // BUGFIX: Prevent double redirects during logout
    // Issue: After logout refreshes the page, some API calls still return auth errors and trigger another redirect
    // Fix: Check the global __IS_LOGGING_OUT__ flag and skip automatic redirects while logout is in progress
    // Related file: src/store/useUserStore.ts
    if (
      typeof window !== 'undefined' &&
      !location.pathname.includes('/login') &&
      isAuthError &&
      !(window as any).__IS_LOGGING_OUT__ // Added: skip redirects while logout is in progress
    ) {
      const currentPath = encodeURIComponent(
        location.pathname + location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
    }

    // Permission error (only on client side)
    if (
      typeof window !== 'undefined' &&
      location.pathname.startsWith('/shifu/') &&
      response.code === 9002
    ) {
      toast({
        title: i18n.t('common.errors.noPermission'),
        variant: 'destructive',
      });
    }

    return Promise.reject(error);
  }
  return response.data ?? response;
};

// ===== Utility Functions =====
const parseJson = (text: string) => {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

// ===== Fetch Wrapper Class =====
export class Request {
  private defaultConfig: RequestInit = {};

  constructor(defaultConfig: RequestInit = {}) {
    this.defaultConfig = defaultConfig;
  }

  private async prepareConfig(
    url: string,
    config: RequestInit,
  ): Promise<{ url: string; config: RequestInit; tokenUsed: string }> {
    const mergedConfig = {
      ...this.defaultConfig,
      ...config,
      headers: {
        ...this.defaultConfig.headers,
        ...config.headers,
      },
    };

    const isFormDataBody =
      typeof FormData !== 'undefined' && config.body instanceof FormData;
    if (isFormDataBody && mergedConfig.headers) {
      delete (mergedConfig.headers as Record<string, string>)['Content-Type'];
    }

    // Handle URL
    let fullUrl = url;
    if (!url.startsWith('http')) {
      if (typeof window !== 'undefined') {
        // Client: use cached API base URL to avoid repeated requests
        const siteHost = await getDynamicApiBaseUrl();
        fullUrl = (siteHost || 'http://localhost:8080') + url;
      } else {
        // Fallback for server-side rendering
        fullUrl = (getStringEnv('baseURL') || 'http://localhost:8080') + url;
      }
    }

    // Add authentication headers
    const token = useUserStore.getState().getToken() || '';
    if (token) {
      mergedConfig.headers = {
        Authorization: `Bearer ${token}`,
        Token: token,
        'X-Request-ID': uuidv4().replace(/-/g, ''),
        ...mergedConfig.headers,
      } as HeadersInit;
    }

    return { url: fullUrl, config: mergedConfig, tokenUsed: token };
  }

  private async interceptFetch(url: string, config: RequestConfig) {
    try {
      const {
        url: fullUrl,
        config: mergedConfig,
        tokenUsed,
      } = await this.prepareConfig(url, config);
      const response = await fetch(fullUrl, mergedConfig);

      if (!response.ok) {
        const isDevelopment = process.env.NODE_ENV === 'development';
        const errorMessage = isDevelopment
          ? `Request failed with status ${response.status}`
          : 'Network request failed';
        throw new ErrorWithCode(errorMessage, response.status);
      }

      const res = await response.json();

      // Check business status code
      if (Object.prototype.hasOwnProperty.call(res, 'code')) {
        const isAuthError = AUTH_ERROR_CODES.has(res.code);
        // If it's login page, we only skip non-auth errors to allow UI to handle business errors
        // But Auth errors (1001, 1004, 1005) MUST be handled by global handler to clear token
        if (location.pathname.includes('/login') && !isAuthError) {
          return res;
        }
        return handleBusinessCode(res, tokenUsed);
      }

      return res;
    } catch (error: any) {
      handleApiError(error);
      throw error;
    }
  }

  // HTTP method wrappers
  get(url: string, config: RequestConfig = {}) {
    return this.interceptFetch(url, { method: 'GET', ...config });
  }

  post(url: string, body: any = {}, config: RequestConfig = {}) {
    const isFormData =
      typeof FormData !== 'undefined' && body instanceof FormData;
    const headers = { ...(config.headers as HeadersInit) };

    const requestConfig: RequestConfig = {
      method: 'POST',
      ...config,
    };

    if (isFormData) {
      if (headers && 'Content-Type' in headers) {
        delete (headers as Record<string, string>)['Content-Type'];
      }
      requestConfig.headers = headers;
      requestConfig.body = body;
    } else {
      try {
        requestConfig.body = JSON.stringify(body ?? {});
      } catch (e) {
        // Payload serialization failed (often due to passing event objects)
        handleApiError(new ErrorWithCode('Invalid request payload', -1));
        throw e;
      }
      requestConfig.headers = {
        'Content-Type': 'application/json',
        ...headers,
      } as HeadersInit;
    }

    return this.interceptFetch(url, requestConfig);
  }

  put(url: string, body: any = {}, config: RequestConfig = {}) {
    const isFormData =
      typeof FormData !== 'undefined' && body instanceof FormData;
    const headers = { ...(config.headers as HeadersInit) };

    const requestConfig: RequestConfig = {
      method: 'PUT',
      ...config,
    };

    if (isFormData) {
      if (headers && 'Content-Type' in headers) {
        delete (headers as Record<string, string>)['Content-Type'];
      }
      requestConfig.headers = headers;
      requestConfig.body = body;
    } else {
      requestConfig.body = JSON.stringify(body ?? {});
      requestConfig.headers = {
        'Content-Type': 'application/json',
        ...headers,
      } as HeadersInit;
    }

    return this.interceptFetch(url, requestConfig);
  }

  delete(url: string, config: RequestConfig = {}) {
    return this.interceptFetch(url, { method: 'DELETE', ...config });
  }

  patch(url: string, body: any = {}, config: RequestConfig = {}) {
    return this.interceptFetch(url, {
      method: 'PATCH',
      body: JSON.stringify(body),
      ...config,
    });
  }
  // Stream request
  async stream(
    url: string,
    body: any = {},
    config: StreamRequestConfig = {},
    callback?: StreamCallback,
  ) {
    const {
      url: fullUrl,
      config: preparedConfig,
      tokenUsed,
    } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = config as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...preparedConfig,
        ...rest,
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const isDevelopment = process.env.NODE_ENV === 'development';
        const errorMessage = isDevelopment
          ? `Request failed with status ${response.status}`
          : 'Network request failed';
        throw new ErrorWithCode(errorMessage, response.status);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Response body is not readable');

      const decoder = new TextDecoder();
      let done = false;
      let text = '';

      const stop = () => {
        done = true;
        controller.abort();
      };

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        let chunkValue = decoder.decode(value);

        if (parseChunk) {
          chunkValue = parseChunk(chunkValue);
        }

        text += chunkValue;

        if (callback) {
          callback(done, text, stop);
        }
      }

      const result = parseJson(text);
      if (typeof result === 'object' && result.code !== undefined) {
        return handleBusinessCode(result, tokenUsed);
      }

      return result;
    } catch (error: any) {
      console.error('Stream request failed:', error);
      throw error;
    }
  }

  // Stream line by line request
  async streamLine(
    url: string,
    body: any = {},
    config: StreamRequestConfig = {},
    callback?: StreamCallback,
  ) {
    const {
      url: fullUrl,
      config: preparedConfig,
      tokenUsed,
    } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = config as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...preparedConfig,
        ...rest,
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const isDevelopment = process.env.NODE_ENV === 'development';
        const errorMessage = isDevelopment
          ? `Request failed with status ${response.status}`
          : 'Network request failed';
        throw new ErrorWithCode(errorMessage, response.status);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Response body is not readable');

      const utf8Decoder = new TextDecoder('utf-8');
      let done = false;
      const stop = () => {
        done = true;
        controller.abort();
      };

      const lines: string[] = [];
      let { value: chunk, done: readerDone } = await reader.read();
      let decodedChunk = chunk
        ? utf8Decoder.decode(chunk, { stream: true })
        : '';
      const re = /\r\n|\n|\r/gm;
      let startIndex = 0;

      // Stream read line processing
      for (;;) {
        const result = re.exec(decodedChunk);
        if (!result) {
          if (readerDone) break;
          const remainder = decodedChunk.substring(startIndex);
          ({ value: chunk, done: readerDone } = await reader.read());
          decodedChunk =
            remainder +
            (chunk ? utf8Decoder.decode(chunk, { stream: true }) : '');
          startIndex = re.lastIndex = 0;
          continue;
        }
        let line = decodedChunk.substring(startIndex, result.index);
        if (parseChunk) {
          line = parseChunk(line);
        }
        lines.push(line);
        if (callback) {
          callback(done, line, stop);
        }
        startIndex = re.lastIndex;
      }

      if (startIndex < decodedChunk.length) {
        let line = decodedChunk.substring(startIndex);
        if (parseChunk) {
          line = parseChunk(line);
        }
        lines.push(line);
        if (callback) {
          callback(done, line, stop);
        }
      }

      if (callback) {
        callback(true, '', stop);
      }

      // Check the last non-empty line for auth error codes to maintain
      // consistent stale-token detection across all request types
      const lastLine = lines.findLast(line => line.trim() !== '');
      if (lastLine) {
        const parsed = parseJson(lastLine);
        if (typeof parsed === 'object' && parsed.code !== undefined) {
          await handleBusinessCode(parsed, tokenUsed);
        }
      }

      return lines;
    } catch (error: any) {
      console.error('StreamLine request failed:', error);
      throw error;
    }
  }
}

// ===== Default Instance Export =====
const defaultConfig = {
  headers: {
    'Content-Type': 'application/json',
  },
};

const request = new Request(defaultConfig);

export default request;
