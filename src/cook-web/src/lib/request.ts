import { getSiteHost } from "@/config/runtime-config";
import { toast } from '@/hooks/use-toast';
import { useUserStore } from "@/c-store/useUserStore";
import { v4 as uuidv4 } from 'uuid';
import { SSE } from 'sse.js';
import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { tokenTool } from "@/c-service/storeUtil";
import i18n from 'i18next';
import { getStringEnv } from "@/c-utils/envUtils";

// ===== Type Definitions =====
export type RequestConfig = RequestInit & { params?: any; data?: any };
export type StreamRequestConfig = RequestInit & { 
  params?: any; 
  data?: any; 
  parseChunk?: (chunkValue: string) => string 
};
export type StreamCallback = (done: boolean, text: string, abort: () => void) => void;

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
      title: error.message || i18n.t("common.networkError"),
      variant: 'destructive',
    });
  }
  
  // Dispatch error event (client side only)
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const apiError = new CustomEvent("apiError", { 
      detail: error, 
      bubbles: true 
    });
    document.dispatchEvent(apiError);
  }
};

// Check response status code and handle business logic
const handleBusinessCode = (response: any) => {
  if (response.code !== 0) {
    const error = new ErrorWithCode(response.message, response.code);
    // Do not show toast for special status codes
    if (![1001].includes(response.code)) {
      handleApiError(error);
    }
    
    // Authentication related errors, redirect to login (client side only)
    if (typeof window !== 'undefined' && location.pathname !== '/login' && [1001, 1004, 1005].includes(response.code)) {
      const currentPath = encodeURIComponent(location.pathname + location.search);
      window.location.href = `/login?redirect=${currentPath}`;
    }
    
    // Permission error (client side only)
    if (typeof window !== 'undefined' && location.pathname.startsWith('/shifu/') && response.code === 9002) {
      toast({
        title: '您当前没有权限访问此内容，请联系管理员获取权限',
        variant: 'destructive',
      });
    }

    // Other errors, reject the promise
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

// Stream line iterator
async function* makeTextStreamLineIterator(reader: ReadableStreamDefaultReader) {
  const utf8Decoder = new TextDecoder("utf-8");
  let { value: chunk, done: readerDone } = await reader.read();
  chunk = chunk ? utf8Decoder.decode(chunk, { stream: true }) : "";
  const re = /\r\n|\n|\r/gm;
  let startIndex = 0;

  for (;;) {
    const result = re.exec(chunk);
    if (!result) {
      if (readerDone) break;
      const remainder = chunk.substr(startIndex);
      ({ value: chunk, done: readerDone } = await reader.read());
      chunk = remainder + (chunk ? utf8Decoder.decode(chunk, { stream: true }) : "");
      startIndex = re.lastIndex = 0;
      continue;
    }
    yield chunk.substring(startIndex, result.index);
    startIndex = re.lastIndex;
  }
  if (startIndex < chunk.length) {
    yield chunk.substr(startIndex);
  }
}

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
      }
    };

    // Handle URL
    let fullUrl = url;
    if (!url.startsWith('http')) {
      if (typeof window !== 'undefined') {
        const siteHost = getSiteHost();
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
        "X-Request-ID": uuidv4().replace(/-/g, ''),
        ...mergedConfig.headers,
      } as HeadersInit;
    }

    return { url: fullUrl, config: mergedConfig };
  }

  private async interceptFetch(url: string, config: RequestConfig) {
    try {
      const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
      const response = await fetch(fullUrl, mergedConfig);
      
      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status}`, response.status);
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

  // Stream request
  async stream(url: string, body: any = {}, config: StreamRequestConfig = {}, callback?: StreamCallback) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = mergedConfig as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...rest,
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status}`, response.status);
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
  async streamLine(url: string, body: any = {}, config: StreamRequestConfig = {}, callback?: StreamCallback) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);

    try {
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...mergedConfig,
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status}`, response.status);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Response body is not readable');

      let done = false;
      const stop = () => {
        done = true;
        controller.abort();
      };
      
      const lines: string[] = [];

      for await (const line of makeTextStreamLineIterator(reader)) {
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

// ===== Axios Instance (for legacy code compatibility) =====
const axiosrequest: AxiosInstance = axios.create({
  withCredentials: false,
  headers: { "Content-Type": "application/json" }
});

// Request interceptor
axiosrequest.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // Use unified base URL logic, consistent with Request class
  if (typeof window !== 'undefined') {
    const siteHost = getSiteHost();
    config.baseURL = siteHost || 'http://localhost:8081';
  } else {
    // Fallback for server-side rendering
    config.baseURL = getStringEnv('baseURL') || 'http://localhost:8081';
  }
  
  const token = tokenTool.get().token;
  if (token) {
    config.headers.token = token;
    config.headers["X-Request-ID"] = uuidv4().replace(/-/g, '');
  }
  
  return config;
});

// Response interceptor
axiosrequest.interceptors.response.use(
  (response: any) => handleBusinessCode(response.data),
  (error: any) => {
    handleApiError(error);
    return Promise.reject(error);
  }
);

// ===== SSE Communication =====
export const SendMsg = (
  token: string,
  chatId: string,
  text: string,
  onMessage?: (response: any) => void
): InstanceType<typeof SSE> => {
  const source = new SSE(`${getStringEnv('baseURL')}/chat/chat-assistant?token=${token}`, {
    headers: { "Content-Type": "application/json" },
    payload: JSON.stringify({
      token,
      msg: text,
      chat_id: chatId,
    }),
  });

  source.addEventListener('message', (event: MessageEvent) => {
    try {
      const response = JSON.parse(event.data);
      onMessage?.(response);
    } catch (e) {
      console.error('SSE message parse error:', e);
    }
  });

  source.addEventListener('error', (event: Event) => {
    console.error('SSE connection error:', event);
  });

  source.stream();
  return source;
};

// ===== Default Instance Export =====
const defaultConfig = {
  headers: {
    'Content-Type': 'application/json',
  },
};

const request = new Request(defaultConfig);

export { axiosrequest };
export default request;