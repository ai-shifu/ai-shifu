/* eslint-disable */
import { getSiteHost } from "@/config/runtime-config";
import { fail } from '@/hooks/use-toast';
import { getToken } from "@/local/local";
import { v4 as uuidv4 } from 'uuid';
import React from 'react';
import ReactDOM from 'react-dom/client';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export type RequestConfig = RequestInit & { params?: any; data?: any };

export type StreamRequestConfig = RequestInit & { params?: any; data?: any, parseChunk?: (chunkValue: string) => string };

export type StreamCallback = (done: boolean, text: string, abort: () => void) => void;

export class ErrorWithCode extends Error {
  code: number;
  constructor(message: string, code: number) {
    super(message);
    this.code = code;
  }
}

function parseJson(text: string) {
  try {
    const result = JSON.parse(text);
    return result;
  } catch (e) {
    return text;
  }
}


async function* makeTextSteamLineIterator(reader: ReadableStreamDefaultReader) {
  const utf8Decoder = new TextDecoder("utf-8");
  let { value: chunk, done: readerDone } = await reader.read();
  chunk = chunk ? utf8Decoder.decode(chunk, { stream: true }) : "";
  const re = /\r\n|\n|\r/gm;
  let startIndex = 0;

  for (; ;) {
    // eslint-disable-next-line prefer-const
    const result = re.exec(chunk);
    if (!result) {
      if (readerDone) {
        break;
      }
      const remainder = chunk.substr(startIndex);
      ({ value: chunk, done: readerDone } = await reader.read());
      chunk =
        remainder + (chunk ? utf8Decoder.decode(chunk, { stream: true }) : "");
      startIndex = re.lastIndex = 0;
      continue;
    }
    yield chunk.substring(startIndex, result.index);
    startIndex = re.lastIndex;
  }
  if (startIndex < chunk.length) {
    // last line didn't end in a newline char
    yield chunk.substr(startIndex);
  }
}

// 封装请求库
export class Request {
  defaultConfig: RequestInit = {};
  baseUrl: string | undefined;
  token: string | undefined;
  constructor(defaultConfig = {}) {
    this.defaultConfig = defaultConfig;
  }
  async prepareConfig(url: string, config: RequestInit) {
    const mergedConfig = {
      ...this.defaultConfig,
      ...config,
      headers: {
        ...this.defaultConfig.headers,
        ...config.headers,
        // "X-API-MODE": "admin",
      }
    };
    let fullUrl = url;
    if (!url.startsWith('http')) {
      if (typeof window !== 'undefined') {
        const siteHost = getSiteHost();
        this.baseUrl = siteHost || 'http://localhost/api';

      }
      fullUrl = this.baseUrl ? this.baseUrl + url : url;
    }

    this.token = await getToken();

    if (this.token) {
      mergedConfig.headers = {
        Authorization: `Bearer ${this.token}`,
        ...mergedConfig.headers,
        "Token": this.token,
        // "X-API-MODE": "admin",
        "X-Request-ID": uuidv4().replace(/-/g, '')
      } as any;
    }

    return {
      url: fullUrl,
      config: mergedConfig
    };
  }
  // intercept request, handle exceptions uniformly
  async interceptFetch(url: string, config: RequestConfig) {
    try {
      const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
      const response = await fetch(fullUrl, mergedConfig);
      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status}`, response.status);
      }

      const res = await response.json();
      // check if there is a code property, use Object API
      if (Object.prototype.hasOwnProperty.call(res, 'code')) {

        if (location.pathname == '/login') {
          return res;
        }
        if (location.pathname != '/login' && (res.code == 1001 || res.code == 1005 || res.code == 1004)) {
            window.location.href = '/login';
        }
        if (location.pathname.startsWith('/shifu/') && res.code == 9002) {
          // todo It should be changed to i18n
          fail('您当前没有权限访问此内容，请联系管理员获取权限');
        }
        if (res.code != 0) {
          throw new ErrorWithCode(res.message , res.code);
        }

        if (res.code == 0) {
          return res.data;
        }

      }
      return res;
    } catch (error: any) {
      fail(error.message)
      throw error;
    }
  }
  async interceptFetchByStreamLine(url: string, config: StreamRequestConfig, callback?: StreamCallback) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
    try {
      const { parseChunk, ...rest } = mergedConfig as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...rest,
        method: 'POST',
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status}`, response.status);
      }

      const data = response.body as any;
      const reader = data.getReader();
      let done = false;
      const stop = () => {
        done = true;
        controller.abort();
      };
      const lines: any = [];

      for await (const line of makeTextSteamLineIterator(reader)) {
        lines.push(line);
        if (callback) {
          await callback(done, line, () => {
            stop();
          });
        }
      }
      if (callback) {
        await callback(true, '', () => {
          stop();
        });
      }
      return lines;

    } catch (error: any) {
      // handle exceptions, such as reporting errors, displaying error prompts, etc.
      console.error('Request failed:', error);
      throw error;
    }
  }

  async interceptFetchByStream(url: string, config: StreamRequestConfig, callback?: StreamCallback) {
    const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);

    try {
      const { parseChunk, ...rest } = mergedConfig as any;
      const controller = new AbortController();
      const response = await fetch(fullUrl, {
        ...rest,
        method: 'POST',
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
      }

      const data = response.body as any;
      const reader = data.getReader();
      const decoder = new TextDecoder();
      let done = false;
      const stop = () => {
        done = true;
        controller.abort();
      };
      let text = '';
      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        let chunkValue = decoder.decode(value);
        if (parseChunk) {
          chunkValue = parseChunk(chunkValue);
        }
        text += chunkValue;
        if (callback) {
          await callback(done, text, () => {
            stop();
          });
        }
      }
      const result = parseJson(text);
      if (typeof result === 'string') {
        return result;
      } else if (typeof result === 'object') {
        if (result.code == 0) {
          return result.data;
        } else if (result.code == -1) {
          throw new ErrorWithCode(result.message, result.code);
        } else {
          return result;
        }
      }

    } catch (error: any) {
      // handle exceptions, such as reporting errors, displaying error prompts, etc.
      console.error('Request failed:', error);
      throw error;
    }
  }

  // wrap get request
  get(url: string, config = {}) {
    return this.interceptFetch(url, {
      method: 'GET',
      ...config,
    } as RequestConfig);
  }

  // wrap post request
  post(url: string, body = {}, config = {}) {
    return this.interceptFetch(url, {
      method: 'POST',
      body: JSON.stringify(body),
      ...config,
    } as RequestConfig);
  }

  stream(url: string, body = {}, config = {}, callback?: StreamCallback) {
    return this.interceptFetchByStream(url, {
      method: 'POST',
      body: JSON.stringify(body),
      ...config,
    } as RequestConfig, callback);
  }

  streamLine(url: string, body = {}, config = {}, callback?: StreamCallback) {
    return this.interceptFetchByStreamLine(url, {
      method: 'POST',
      body: JSON.stringify(body),
      ...config,
    } as RequestConfig, callback);
  }
  async fetch(url: string, config: RequestConfig) {
    try {
      const { url: fullUrl, config: mergedConfig } = await this.prepareConfig(url, config);
      const response = await fetch(fullUrl, {
        ...mergedConfig,
        method: "POST"
      });
      if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
      }
      return response;
    } catch (error: any) {
      // handle exceptions, such as reporting errors, displaying error prompts, etc.
      console.error('Request failed:', error.message);
      fail(error.message);
      throw error;
    }
  }
  // wrap other request methods, such as put, delete, etc.
  // put(url, body = null, config = {}) {}
  // delete(url, config = {}) {}
}

// example usage
const defaultConfig = {
  headers: {
    'Content-Type': 'application/json',
  },
  // add other default configuration items
};

const request = new Request(defaultConfig);
export default request;
