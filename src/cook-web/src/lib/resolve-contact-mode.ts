export type ContactMode = 'email' | 'phone';

type LoginMethodsInput = string[] | string | null | undefined;

type DefaultLoginInput = string | null | undefined;

const normalizeMethods = (methods: LoginMethodsInput): string[] => {
  if (Array.isArray(methods)) {
    return methods
      .map(method => method.trim().toLowerCase())
      .filter(Boolean);
  }
  if (typeof methods === 'string') {
    return methods
      .split(',')
      .map(method => method.trim().toLowerCase())
      .filter(Boolean);
  }
  return [];
};

export const resolveContactMode = (
  loginMethodsEnabled: LoginMethodsInput,
  defaultLoginMethod: DefaultLoginInput,
): ContactMode => {
  const methods = normalizeMethods(loginMethodsEnabled);
  const hasEmail = methods.includes('email');
  const hasPhone = methods.includes('phone');
  const normalizedDefault = (defaultLoginMethod || '').trim().toLowerCase();

  if (hasEmail && !hasPhone) {
    return 'email';
  }
  if (hasPhone && !hasEmail) {
    return 'phone';
  }
  if (hasEmail && hasPhone) {
    return normalizedDefault === 'email' ? 'email' : 'phone';
  }
  if (normalizedDefault === 'email') {
    return 'email';
  }
  return 'phone';
};
