// Debug helper for listen mode audio diagnostics.
export const shouldListenDebugAlert = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }
  const search = window.location?.search ?? '';
  if (search.includes('listenDebug=1')) {
    return true;
  }
  try {
    return window.localStorage?.getItem('listenDebug') === '1';
  } catch {
    return false;
  }
};

const safeStringify = (payload: Record<string, unknown>): string => {
  try {
    return JSON.stringify(payload);
  } catch {
    return '[unserializable]';
  }
};

export const emitListenDebugAlert = (
  message: string,
  data?: Record<string, unknown>,
): void => {
  if (!shouldListenDebugAlert()) {
    return;
  }
  const suffix = data ? `\n${safeStringify(data)}` : '';
  window.alert(`[listen-debug] ${message}${suffix}`);
};
