import { UserRole } from '../c-types/user-roles';

describe('User Role Types', () => {
  it('should have correct user role enum values', () => {
    expect(UserRole.GUEST).toBe('guest');
    expect(UserRole.REGISTERED).toBe('registered');
    expect(UserRole.CREATOR).toBe('creator');
    expect(UserRole.ADMIN).toBe('admin');
  });
});