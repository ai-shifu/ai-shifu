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
    // BUGFIX: Global flag to prevent double page load during logout.
    // Used to block automatic redirect logic in request.ts during the logout process.
    // Related files: src/store/useUserStore.ts, src/lib/request.ts
    __IS_LOGGING_OUT__?: boolean;
  }
}
