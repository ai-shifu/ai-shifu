'use client';

export const DEBUG_QUERY_PARAM = 'debug';
export const DEBUG_QUERY_ENABLED_VALUE = '1';

export type DebugConsoleLevel = 'log' | 'info' | 'warn' | 'error';

export type DebugConsoleEntry = {
  id: string;
  level: DebugConsoleLevel;
  message: string;
  timestamp: string;
};

const MAX_DEBUG_MESSAGE_LENGTH = 4000;

const safeSerialize = (value: unknown): string => {
  if (typeof value === 'string') {
    return value;
  }

  if (value instanceof Error) {
    return JSON.stringify(
      {
        name: value.name,
        message: value.message,
        stack: value.stack,
      },
      null,
      2,
    );
  }

  try {
    return JSON.stringify(
      value,
      (_key, currentValue) => {
        if (currentValue instanceof Error) {
          return {
            name: currentValue.name,
            message: currentValue.message,
            stack: currentValue.stack,
          };
        }

        return currentValue;
      },
      2,
    );
  } catch {
    return String(value);
  }
};

export const formatConsoleArgs = (args: unknown[]) => {
  const normalizedMessage = args
    .map(item => safeSerialize(item))
    .join(' ')
    .trim();

  if (!normalizedMessage) {
    return '';
  }

  if (normalizedMessage.length <= MAX_DEBUG_MESSAGE_LENGTH) {
    return normalizedMessage;
  }

  return `${normalizedMessage.slice(0, MAX_DEBUG_MESSAGE_LENGTH)}...`;
};

export const isRuntimeDebugEnabled = () => {
  if (typeof window === 'undefined') {
    return false;
  }

  const debugValue = new URLSearchParams(window.location.search).get(
    DEBUG_QUERY_PARAM,
  );
  return debugValue === DEBUG_QUERY_ENABLED_VALUE;
};

const emitDebugConsole = (
  level: DebugConsoleLevel,
  label: string,
  payload?: unknown,
) => {
  if (!isRuntimeDebugEnabled()) {
    return;
  }

  if (payload === undefined) {
    console[level](label);
    return;
  }

  console[level](label, payload);
};

export const debugLog = (label: string, payload?: unknown) => {
  emitDebugConsole('log', label, payload);
};

export const debugInfo = (label: string, payload?: unknown) => {
  emitDebugConsole('info', label, payload);
};

export const debugWarn = (label: string, payload?: unknown) => {
  emitDebugConsole('warn', label, payload);
};

export const debugError = (label: string, payload?: unknown) => {
  emitDebugConsole('error', label, payload);
};
