import { environment } from '@/config/environment';
import { toast } from '@/hooks/use-toast';
import { useUserStore } from "@/c-store/useUserStore";
import { v4 as uuidv4 } from 'uuid';
import { SSE } from 'sse.js';
import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { tokenTool } from "@/c-service/storeUtil";
import i18n from 'i18next';
import { getStringEnv } from "@/c-utils/envUtils";

// ===== 类型定义 =====
export type RequestConfig = RequestInit & { params?: any; data?: any };

export type StreamCallback = (data: any) => void;

export type StreamRequestConfig = RequestInit & {
  onMessage?: StreamCallback;
  onError?: (error: any) => void;
  onOpen?: () => void;
  onClose?: () => void;
};

// ===== 错误处理 =====
class ErrorWithCode extends Error {
  constructor(message: string, public code: number) {
    super(message);
    this.name = 'ErrorWithCode';
  }
}

// 统一错误处理函数
const handleApiError = (error: any, showToast = true) => {
  if (showToast) {
    toast({
      title: error.message || i18n.t("common.networkError"),
      variant: 'destructive',
    });
  }

  // 派发错误事件 (仅在客户端执行)
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const apiError = new CustomEvent("apiError", {
      detail: error,
      bubbles: true
    });
    document.dispatchEvent(apiError);
  }
};

// 检查响应状态码并处理业务逻辑
const handleBusinessCode = (response: any) => {
  if (response.code !== 0) {
    // 特殊状态码不显示toast
    if (![1001].includes(response.code)) {
      handleApiError(response);
    }

    // 认证相关错误，跳转登录 (仅在客户端执行)
    if (typeof window !== 'undefined' && location.pathname !== '/login' && [1001, 1004, 1005].includes(response.code)) {
      window.location.href = '/login';
    }

    // 权限错误 (仅在客户端执行)
    if (typeof window !== 'undefined' && location.pathname.startsWith('/shifu/') && response.code === 9002) {
      toast({
        title: '您当前没有权限访问此内容，请联系管理员获取权限',
        variant: 'destructive',
      });
    }

    return Promise.reject(response);
  }
  return response.data || response;
};

// ===== 动态获取API基础URL =====
let cachedApiBaseUrl: string = '';

/**
 * 动态获取API基础URL
 * 在客户端运行时获取，支持运行时环境变量
 */
async function getDynamicApiBaseUrl(): Promise<string> {
  // 如果已经缓存，直接返回
  if (cachedApiBaseUrl && cachedApiBaseUrl !== '') {
    return cachedApiBaseUrl;
  }

  try {
    // 1. 尝试从 /api/config 获取运行时配置
    const response = await fetch('/api/config');
    if (response.ok) {
      const config = await response.json();
      if (config.apiBaseUrl) {
        cachedApiBaseUrl = config.apiBaseUrl;
        return cachedApiBaseUrl;
      }
    }
  } catch (error) {
    console.warn('Failed to fetch runtime config:', error);
  }

  // 2. 使用环境变量或默认值
  const fallbackUrl = environment.apiBaseUrl || 'http://localhost:8081';
  cachedApiBaseUrl = fallbackUrl;
  return fallbackUrl;
}

// ===== Request 类 =====
export class Request {
  private defaultConfig: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  private async prepareConfig(url: string, config: RequestInit) {
    const mergedConfig = {
      ...this.defaultConfig,
      ...config,
      headers: {
        ...this.defaultConfig.headers,
        ...config.headers,
      }
    };

    // 处理URL
    let fullUrl = url;
    if (!url.startsWith('http')) {
      if (typeof window !== 'undefined') {
        // 客户端：动态获取API基础URL
        const siteHost = await getDynamicApiBaseUrl();
        fullUrl = (siteHost || 'http://localhost:8081') + url;
      } else {
        // 服务端渲染时的后备方案
        fullUrl = (getStringEnv('baseURL') || 'http://localhost:8081') + url;
      }
    }

    // 添加认证头
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

      // 检查业务状态码
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

  async get(url: string, config: RequestConfig = {}) {
    return this.interceptFetch(url, { ...config, method: 'GET' });
  }

  async post(url: string, data?: any, config: RequestConfig = {}) {
    return this.interceptFetch(url, {
      ...config,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async put(url: string, data?: any, config: RequestConfig = {}) {
    return this.interceptFetch(url, {
      ...config,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete(url: string, config: RequestConfig = {}) {
    return this.interceptFetch(url, { ...config, method: 'DELETE' });
  }

  async patch(url: string, data?: any, config: RequestConfig = {}) {
    return this.interceptFetch(url, {
      ...config,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async stream(url: string, data?: any, config: StreamRequestConfig = {}) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
    const token = useUserStore.getState().getToken();

    const source = new SSE(fullUrl, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Token: token,
        "X-Request-ID": uuidv4().replace(/-/g, ''),
        ...mergedConfig.headers,
      },
      payload: data ? JSON.stringify(data) : undefined,
    });

    source.addEventListener('message', (event: MessageEvent) => {
      try {
        const response = JSON.parse(event.data);
        config.onMessage?.(response);
      } catch (e) {
        console.error('SSE message parse error:', e);
      }
    });

    source.addEventListener('error', (event: Event) => {
      console.error('SSE connection error:', event);
      config.onError?.(event);
    });

    source.addEventListener('open', () => {
      config.onOpen?.();
    });

    source.addEventListener('close', () => {
      config.onClose?.();
    });

    source.stream();
    return source;
  }

  async streamLine(url: string, data?: any, config: StreamRequestConfig = {}) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
    const token = useUserStore.getState().getToken();

    const response = await fetch(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Token: token,
        "X-Request-ID": uuidv4().replace(/-/g, ''),
        ...mergedConfig.headers,
      },
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.body) {
      throw new Error('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    const processStream = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                config.onMessage?.(data);
              } catch (e) {
                console.error('Stream line parse error:', e);
              }
            }
          }
        }
      } catch (error) {
        config.onError?.(error);
      } finally {
        config.onClose?.();
      }
    };

    processStream();
  }
}

// 创建默认实例
const http = new Request();

// 导出默认实例和方法
export default http;

// ===== Axios 实例（兼容旧代码）=====
const axiosrequest: AxiosInstance = axios.create({
  withCredentials: false,
  headers: { "Content-Type": "application/json" }
});

// 请求拦截器
axiosrequest.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  // 使用统一的 base URL 获取逻辑，与 Request 类保持一致
  if (typeof window !== 'undefined') {
    // 客户端：动态获取API基础URL
    const siteHost = await getDynamicApiBaseUrl();
    config.baseURL = siteHost || 'http://localhost:8081';
  } else {
    // 服务端渲染时的后备方案
    config.baseURL = getStringEnv('baseURL') || 'http://localhost:8081';
  }

  const token = tokenTool.get().token;
  if (token) {
    config.headers.token = token;
    config.headers["X-Request-ID"] = uuidv4().replace(/-/g, '');
  }

  return config;
});

// 响应拦截器
axiosrequest.interceptors.response.use(
  (response: any) => {
    if (response.data.code !== 0) {
      if (![1001].includes(response.data.code)) {
        toast({
          title: response.data.message || i18n.t("common.networkError"),
          variant: 'destructive',
        });
      }
      const apiError = new CustomEvent("apiError", { detail: response.data, bubbles: true });
      document.dispatchEvent(apiError);
      return Promise.reject(response.data);
    }
    return response.data;
  },
  (error: any) => {
    handleApiError(error);
    return Promise.reject(error);
  }
);

export { axiosrequest };

// ===== SSE 通信 =====
export const SendMsg = async (
  token: string,
  chatId: string,
  text: string,
  onMessage?: (response: any) => void
): Promise<InstanceType<typeof SSE>> => {
  const baseURL = await getDynamicApiBaseUrl();
  const source = new SSE(`${baseURL}/chat/chat-assistant?token=${token}`, {
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
