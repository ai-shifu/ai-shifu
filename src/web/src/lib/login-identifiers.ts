export type LoginIdentifierType = 'email' | 'phone';

type LoginMethodsInput = ReadonlyArray<string> | string | null | undefined;

/**
 * Maps deployment login methods to their configured identifier types.
 * Google contributes an email identifier; unknown methods contribute none.
 * The result is deduplicated in phone/email order and says nothing about the
 * current user's login method or the identifiers stored on an account.
 */
export const resolveLoginIdentifierTypes = (
  loginMethodsEnabled: LoginMethodsInput,
): ReadonlyArray<LoginIdentifierType> => {
  const methods =
    typeof loginMethodsEnabled === 'string'
      ? loginMethodsEnabled.split(',')
      : loginMethodsEnabled || [];
  const normalizedMethods = methods.map(method => method.trim().toLowerCase());
  const identifierTypes: LoginIdentifierType[] = [];

  if (normalizedMethods.includes('phone')) {
    identifierTypes.push('phone');
  }
  if (
    normalizedMethods.includes('email') ||
    normalizedMethods.includes('google')
  ) {
    identifierTypes.push('email');
  }
  return identifierTypes;
};

/**
 * Preserves the selection policy for existing interfaces with one account field.
 * A sole configured type wins. Otherwise only an explicit email default selects
 * email; phone is the legacy fallback, including when the default is Google.
 * This UI policy is not a deployment-wide preference or a user's login history.
 * Interfaces that support multiple types should use the collection directly.
 */
export const selectSingleLoginIdentifierType = (
  loginIdentifierTypes: ReadonlyArray<LoginIdentifierType>,
  defaultLoginMethod: string | null | undefined,
): LoginIdentifierType => {
  const hasEmail = loginIdentifierTypes.includes('email');
  const hasPhone = loginIdentifierTypes.includes('phone');

  if (hasEmail && !hasPhone) {
    return 'email';
  }
  if (hasPhone && !hasEmail) {
    return 'phone';
  }
  return (defaultLoginMethod || '').trim().toLowerCase() === 'email'
    ? 'email'
    : 'phone';
};
