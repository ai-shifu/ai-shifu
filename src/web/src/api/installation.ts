import request from '@/lib/request';
import type { UserInfo } from '@/types';

export interface InstallationStatus {
  setup_required: boolean;
  local_admin_login_enabled: boolean;
}

export interface InstallationSession {
  userInfo: UserInfo;
  token: string;
}

export interface LocalAdministratorCredentials {
  identifier: string;
  password: string;
  language: string;
}

const requestOptions = { skipErrorToast: true };

export const getInstallationStatus = async (): Promise<InstallationStatus> => {
  const value: unknown = await request.get('/api/installation/status', {
    ...requestOptions,
    cache: 'no-store',
  });
  if (
    !value ||
    typeof value !== 'object' ||
    typeof (value as InstallationStatus).setup_required !== 'boolean' ||
    typeof (value as InstallationStatus).local_admin_login_enabled !== 'boolean'
  ) {
    throw new Error('Invalid installation status response');
  }
  return value as InstallationStatus;
};

export const initializeAdministrator = (
  payload: LocalAdministratorCredentials & { setup_token: string },
): Promise<InstallationSession> =>
  request.post('/api/installation/initialize', payload, requestOptions);

export const loginLocalAdministrator = (
  payload: LocalAdministratorCredentials,
): Promise<InstallationSession> =>
  request.post('/api/installation/login', payload, requestOptions);
