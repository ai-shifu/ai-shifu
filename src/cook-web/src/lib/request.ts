import { useUserStore } from '@/store/useUserStore';
import { getStringEnv } from '@/c-utils/envUtils';
import { getDynamicApiBaseUrl } from '@/config/environment';
import { toast } from '@/hooks/useToast';
import i18n from 'i18next';
import { v4 as uuidv4 } from 'uuid';

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
      title: error.message || i18n.t('common.networkError'),
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

// Check response status code and handle business logic
const handleBusinessCode = (response: any) => {
  const error = new ErrorWithCode(
    response.message || i18n.t('common.unknownError'),
    response.code || -1,
  );

  if (response.code !== 0) {
    // Special status codes do not show toast
    if (![1001].includes(response.code)) {
      handleApiError(error);
    }

    // Authentication related errors, redirect to login (only on client side)
    if (
      typeof window !== 'undefined' &&
      location.pathname !== '/login' &&
      [1001, 1004, 1005].includes(response.code)
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
        title: i18n.t('errors.noPermission'),
        variant: 'destructive',
      });
    }

    return Promise.reject(error);
  }
  return response.data || response;
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

  private async prepareConfig(url: string, config: RequestInit) {
    const mergedConfig = {
      ...this.defaultConfig,
      ...config,
      headers: {
        ...this.defaultConfig.headers,
        ...config.headers,
      },
    };

    // Handle URL
    let fullUrl = url;
    if (!url.startsWith('http')) {
      if (typeof window !== 'undefined') {
        // Client: use cached API base URL to avoid repeated requests
        const siteHost = await getDynamicApiBaseUrl();
        fullUrl = (siteHost || 'http://localhost:8081') + url;
      } else {
        // Fallback for server-side rendering
        fullUrl = (getStringEnv('baseURL') || 'http://localhost:8081') + url;
      }
    }

    // Add authentication headers
    const token = useUserStore.getState().getToken();
    if (token) {
      mergedConfig.headers = {
        Authorization: `Bearer ${token}`,
        Token: token,
        'X-Request-ID': uuidv4().replace(/-/g, ''),
        ...mergedConfig.headers,
      } as HeadersInit;
    }

    return { url: fullUrl, config: mergedConfig };
  }

  private async interceptFetch(url: string, config: RequestConfig) {
    try {
      const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(
        url,
        config,
      );
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
        if (location.pathname === '/login') return res;
        return handleBusinessCode(res);
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
    return this.interceptFetch(url, {
      method: 'POST',
      body: JSON.stringify(body),
      ...config,
    });
  }

  put(url: string, body: any = {}, config: RequestConfig = {}) {
    return this.interceptFetch(url, {
      method: 'PUT',
      body: JSON.stringify(body),
      ...config,
    });
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
    const { url: fullUrl } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = config as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
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
        return handleBusinessCode(result);
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
    const { url: fullUrl } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = config as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
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
