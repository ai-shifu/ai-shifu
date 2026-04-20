import { buildAdminMenuItems } from './admin-menu';

describe('buildAdminMenuItems', () => {
  const t = (key: string) => key;

  test('excludes operations entry for non-operators', () => {
    const menuItems = buildAdminMenuItems({ t, isOperator: false });

    expect(menuItems.map(item => item.href)).toEqual([
      '/admin',
      '/admin/orders',
      '/admin/dashboard',
      '/admin/billing',
    ]);
  });

  test('includes operations entry for operators', () => {
    const menuItems = buildAdminMenuItems({ t, isOperator: true });

    expect(menuItems.map(item => item.href)).toEqual([
      '/admin',
      '/admin/orders',
      '/admin/dashboard',
      '/admin/billing',
      undefined,
    ]);
    expect(menuItems.at(-1)).toMatchObject({
      id: 'operations',
      label: 'common.core.operations',
      children: [
        {
          id: 'operations-course',
          label: 'common.core.courseManagement',
          href: '/admin/operations',
        },
      ],
    });
  });
});
