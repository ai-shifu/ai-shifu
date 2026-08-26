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
          id: 'operations-brand-payments',
          label: 'common.core.brandPaymentsManagement',
          href: '/admin/operations/billing',
        },
        {
          id: 'operations-config',
          label: 'common.core.rateManagement',
          href: '/admin/operations/config',
        },
        {
          id: 'operations-credit-notification',
          label: 'common.core.creditNotificationManagement',
          href: '/admin/operations/credit-notifications',
        },
        {
          id: 'operations-referrals',
          label: 'common.core.referralInvitation',
          href: '/admin/operations/referrals',
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

  test('shows package management in the requested Stripe operator menu order', () => {
    const menuItems = buildAdminMenuItems({
      t,
      isOperator: true,
      showPackageManagement: true,
    });

    expect(menuItems.at(-1)?.children?.map(item => item.id)).toEqual([
      'operations-course',
      'operations-user',
      'operations-order',
      'operations-promotion',
      'operations-package-management',
      'operations-brand-payments',
      'operations-config',
      'operations-credit-notification',
      'operations-referrals',
      'operations-voice-clone',
      'operations-profile-onboarding',
    ]);
  });
});
