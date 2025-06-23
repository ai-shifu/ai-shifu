declare module 'sse.js' {
  export class SSE {
    constructor(url: string, options?: {
      headers?: Record<string, string>;
      payload?: string;
      method?: string;
      withCredentials?: boolean;
    });

    addEventListener(event: string, listener: (event: MessageEvent | Event) => void): void;
    removeEventListener(event: string, listener: (event: MessageEvent | Event) => void): void;
    stream(): void;
    close(): void;
  }
}
