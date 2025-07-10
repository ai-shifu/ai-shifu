import { UserInfo } from '@/c-types/index';

export const mockUserData = {
  // Guest user (no token or faked token)
  guestUser: {
    userInfo: null,
    isGuest: true,
    isLoggedIn: false,
    token: { token: 'fake-token-123', faked: true }
  },

  // Registered user
  registeredUser: {
    userInfo: {
      user_id: '1',
      username: 'john_doe',
      avatar: 'https://example.com/avatar.jpg',
      phone: '+1234567890',
      language: 'en',
      email: 'john@example.com'
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-123', faked: false }
  },

  // Creator user
  creatorUser: {
    userInfo: {
      user_id: '2',
      username: 'jane_creator',
      avatar: 'https://example.com/avatar2.jpg',
      phone: '+1234567891',
      language: 'en',
      email: 'jane@example.com',
      role: 'creator',
      is_creator: true,
      can_create: true
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-456', faked: false }
  },

  // Admin user
  adminUser: {
    userInfo: {
      user_id: '3',
      username: 'admin_user',
      avatar: 'https://example.com/avatar3.jpg',
      phone: '+1234567892',
      language: 'en',
      email: 'admin@example.com',
      role: 'admin',
      is_admin: true,
      can_create: true
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-789', faked: false }
  },

  // Creator with alternative flags
  creatorUserAlt: {
    userInfo: {
      user_id: '4',
      username: 'creator_alt',
      avatar: 'https://example.com/avatar4.jpg',
      phone: '+1234567893',
      language: 'en',
      email: 'creator@example.com',
      is_creator: true
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-alt', faked: false }
  },

  // Admin with alternative flags
  adminUserAlt: {
    userInfo: {
      user_id: '5',
      username: 'admin_alt',
      avatar: 'https://example.com/avatar5.jpg',
      phone: '+1234567894',
      language: 'en',
      email: 'admin-alt@example.com',
      is_admin: true
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-admin', faked: false }
  },

  // Premium user
  premiumUser: {
    userInfo: {
      user_id: '6',
      username: 'premium_user',
      avatar: 'https://example.com/avatar6.jpg',
      phone: '+1234567895',
      language: 'en',
      email: 'premium@example.com',
      premium: true
    } as UserInfo,
    isGuest: false,
    isLoggedIn: true,
    token: { token: 'valid-token-premium', faked: false }
  },

  // User with no login check
  uncheckedUser: {
    userInfo: null,
    isGuest: false,
    isLoggedIn: false,
    token: { token: null, faked: true }
  }
};

export const mockTokenTool = {
  get: jest.fn(),
  set: jest.fn()
};

export const mockUserStore = {
  getState: jest.fn(),
  subscribe: jest.fn(),
  destroy: jest.fn()
};

export const createMockUserStore = (userData: any) => ({
  ...userData,
  initialize: jest.fn(),
  updateUserInfo: jest.fn(),
  refreshUserInfo: jest.fn(),
  logout: jest.fn(),
  login: jest.fn(),
  setProfile: jest.fn(),
  fetchProfile: jest.fn()
});