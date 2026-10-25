export type InstallationSurface =
  | 'setup'
  | 'local_login'
  | 'local_password_change';
export type InstallationFailureCategory =
  | 'none'
  | 'credentials_rejected'
  | 'transport_or_service'
  | 'session_unavailable';

export const INSTALLATION_AUTH_EXPOSURE = 'installation_auth_exposure';
export const INSTALLATION_AUTH_ATTEMPT = 'installation_auth_attempt';
export const INSTALLATION_AUTH_RESULT = 'installation_auth_result';

export const buildInstallationExposure = (surface: InstallationSurface) => ({
  surface,
});

export const buildInstallationResult = (
  surface: InstallationSurface,
  outcome: 'success' | 'failed',
  failureCategory: InstallationFailureCategory,
) => ({ surface, outcome, failure_category: failureCategory });
