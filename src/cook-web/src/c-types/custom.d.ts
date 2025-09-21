declare module 'sse.js';
declare module '*.scss';
declare module '*.css';
declare module '*.png';
declare module '*.jpg';
declare module '*.svg';
declare module '*.gif';
declare module '*.md';

declare global {
  interface Window {
    // BUGFIX: 防止退出登录时页面双重加载的全局标志
    // 用于在logout过程中阻止request.ts的自动跳转逻辑
    // 相关文件：src/store/useUserStore.ts, src/lib/request.ts
    __IS_LOGGING_OUT__?: boolean;
  }
}
