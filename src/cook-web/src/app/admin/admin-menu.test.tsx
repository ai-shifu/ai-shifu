import { buildAdminMenuItems } from './admin-menu';

describe('buildAdminMenuItems', () => {
  const t = (key: string) => key;

  test('excludes operations entry for non-operators', () => {
    const menuItems = buildAdminMenuItems({ t, isOperator: false });

    expect(menuItems.map(item => item.href)).toEqual([
      '/admin',
      '/admin/orders',
      '/admin/dashboard',
    ]);
  });

  test('includes operations entry for operators', () => {
    const menuItems = buildAdminMenuItems({ t, isOperator: true });

    expect(menuItems.map(item => item.href)).toEqual([
      '/admin',
      '/admin/orders',
      '/admin/dashboard',
      '/admin/operations',
    ]);
    expect(menuItems.at(-1)?.label).toBe('common.core.operations');
  });
});
