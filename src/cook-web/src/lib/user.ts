/**
 * User ID Management for MDF Convert
 * Generates and stores anonymous user ID in localStorage
 */

const USER_ID_KEY = 'mdf_user_id';
const USER_ID_EXPIRY_DAYS = 30;

interface UserIdData {
  id: string;
  createdAt: number;
  expiresAt: number;
}

/**
 * Generate a random user ID
 */
function generateUserId(): string {
  return `user_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
}

/**
 * Get or create user ID
 */
export function getUserId(): string {
  if (typeof window === 'undefined') {
    // SSR: return temporary ID
    return 'ssr_' + Date.now();
  }

  try {
    const stored = localStorage.getItem(USER_ID_KEY);
    if (stored) {
      const data: UserIdData = JSON.parse(stored);
      if (Date.now() < data.expiresAt) {
        return data.id;
      }
    }
  } catch (error) {
    console.warn('Failed to retrieve user ID from localStorage:', error);
  }

  // Generate new user ID
  const userId = generateUserId();
  const data: UserIdData = {
    id: userId,
    createdAt: Date.now(),
    expiresAt: Date.now() + USER_ID_EXPIRY_DAYS * 24 * 60 * 60 * 1000,
  };

  try {
    localStorage.setItem(USER_ID_KEY, JSON.stringify(data));
  } catch (error) {
    console.warn('Failed to save user ID to localStorage:', error);
  }

  return userId;
}

/**
 * Refresh user ID expiry time
 */
export function refreshUserIdExpiry(): void {
  if (typeof window === 'undefined') return;

  try {
    const stored = localStorage.getItem(USER_ID_KEY);
    if (stored) {
      const data: UserIdData = JSON.parse(stored);
      data.expiresAt = Date.now() + USER_ID_EXPIRY_DAYS * 24 * 60 * 60 * 1000;
      localStorage.setItem(USER_ID_KEY, JSON.stringify(data));
    }
  } catch (error) {
    console.warn('Failed to refresh user ID expiry:', error);
  }
}
