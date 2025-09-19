export const ERROR_CODES = {
  SUCCESS: 0,
  UNAUTHORIZED: 1001,
  TOKEN_EXPIRED: 1004,
  INVALID_TOKEN: 1005,
  NO_PERMISSION: 9002,
} as const;

export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES];
