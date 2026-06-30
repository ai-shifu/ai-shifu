import { buildAdminMenuItems } from './admin-menu';

describe('buildAdminMenuItems', () => {
  const t = (key: string) => key;

  test('excludes operations entry for non-operators', () => {
    const menuItems = buildAdminMenuItems({ t, isOperator: false });

    expect(menuItems.map(item => item.href)).toEqual([
      '/admin',
      '/admin/orders',
      '/admin/dashboard',
      '/admin/referral',
    ]);
  });

  test('excludes referral invite entry when referral is unavailable', () => {
    const options = { t, isOperator: false, showReferralInvite: false };
    const menuItems = buildAdminMenuItems(options);

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
      '/admin/referral',
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
        {
          id: 'operations-user',
          label: 'common.core.userManagement',
          href: '/admin/operations/users',
        },
        {
          id: 'operations-order',
          label: 'common.core.orderManagement',
          href: '/admin/operations/orders',
        },
        {
          id: 'operations-promotion',
          label: 'common.core.promotionManagement',
          href: '/admin/operations/promotions',
        },
        {
          id: 'operations-credit-notification',
          label: 'common.core.creditNotificationManagement',
          href: '/admin/operations/credit-notifications',
        },
        {
          id: 'operations-voice-clone',
          label: 'common.core.voiceCloneManagement',
          href: '/admin/operations/voice-clones',
        },
        {
          id: 'operations-profile-onboarding',
          label: 'common.core.profileOnboardingManagement',
          href: '/admin/operations/profile-onboarding',
        },
      ],
    });
  });
});
