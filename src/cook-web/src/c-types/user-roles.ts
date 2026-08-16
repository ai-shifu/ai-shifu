export enum UserRole {
  GUEST = 'guest',
  REGISTERED = 'registered',
  CREATOR = 'creator',
  ADMIN = 'admin',
}

export interface UserRoleInfo {
  role: UserRole;
  isGuest: boolean;
  isRegistered: boolean;
  isCreator: boolean;
  isAdmin: boolean;
  hasValidToken: boolean;
  permissions: string[];
}
