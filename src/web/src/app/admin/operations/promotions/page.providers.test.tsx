import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import {
  mockGetCoupons,
  mockGetPackageCampaigns,
  mockPublishPackageCampaignProviderDiscounts,
  mockRetryPackageCampaignProviderDiscounts,
  mockPaymentTracking,
  mockToast,
  mockUpdatePackageCampaignStatus,
  setMockPaymentProviders,
} from './promotionsTestUtils.test-support';
import Page from './page';
import {
  isPackageCampaignProviderDiscountSynced,
  resolvePackageCampaignProviderDiscountLabel,
  shouldShowPackageCampaignProviderRetry,
  shouldShowPackageCampaignProviderRetire,
} from './promotionPageShared';
const provider = (name: string) => ({
  provider: name,
  label_key: name,
  catalog: true,
  discounts: true,
});
async function openActions() {
  render(<Page />);
  await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.tabs.packageCampaigns',
    }),
  );
  await screen.findByText('Spring Package Promo');
  const buttons = screen.getAllByRole('button', { name: 'common.core.more' });
  fireEvent.click(buttons[buttons.length - 1]);
}
test.each(['success', 'reject', 'throw'])(
  'publishes all capable channels explicitly, excluding local-only, with analytics %s',
  async mode => {
    setMockPaymentProviders({
      items: [
        provider('stripe'),
        provider('fixture-catalog'),
        { ...provider('pingxx'), catalog: false, discounts: false },
      ],
      discount_sync_required: true,
    });
    if (mode === 'reject')
      mockPaymentTracking.mockRejectedValue(new Error('offline'));
    if (mode === 'throw')
      mockPaymentTracking.mockImplementation(() => {
        throw new Error('offline');
      });
    await openActions();
    expect(mockPaymentTracking).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByText(
        'module.operationsPromotion.actions.publishProviderDiscounts',
      ),
    );
    await waitFor(() =>
      expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenCalledTimes(
        2,
      ),
    );
    expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenNthCalledWith(
      1,
      { campaign_bid: 'campaign-1', provider: 'stripe' },
    );
    expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenNthCalledWith(
      2,
      { campaign_bid: 'campaign-1', provider: 'fixture-catalog' },
    );
    await waitFor(() => expect(mockPaymentTracking).toHaveBeenCalledTimes(2));
    expect(mockPaymentTracking.mock.calls).toEqual([
      [
        'admin_payment_discount_publish_start',
        { operation: 'publish', provider_count: 2 },
      ],
      [
        'admin_payment_discount_publish_result',
        { operation: 'publish', provider_count: 2, outcome: 'success' },
      ],
    ]);
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith({
        description:
          'module.operationsPromotion.messages.packageCampaignProviderPublished',
      }),
    );
  },
);
test('attempts other providers after a transport failure and refreshes persisted state', async () => {
  setMockPaymentProviders({
    items: [provider('stripe'), provider('fixture-catalog')],
    discount_sync_required: true,
  });
  mockPublishPackageCampaignProviderDiscounts.mockRejectedValueOnce(
    new Error('provider unavailable'),
  );
  await openActions();
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.publishProviderDiscounts',
    ),
  );
  await waitFor(() =>
    expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenCalledTimes(
      2,
    ),
  );
  await waitFor(() => expect(mockGetPackageCampaigns).toHaveBeenCalledTimes(2));
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'publish', provider_count: 2, outcome: 'failed' },
  );
});
test('partial publication is not synced and remains retryable', () => {
  const item = {
    benefit_type: 'discount',
    product_count: 1,
    provider_discount_summary: {
      total: 1,
      active: 1,
      missing_provider_count: 1,
    },
  } as any;
  expect(isPackageCampaignProviderDiscountSynced(item)).toBe(false);
  expect(shouldShowPackageCampaignProviderRetry(item)).toBe(true);
  expect(resolvePackageCampaignProviderDiscountLabel(key => key, item)).toBe(
    'packageCampaign.providerDiscountPartial',
  );
  item.provider_discount_summary.missing_provider_count = 0;
  expect(isPackageCampaignProviderDiscountSynced(item)).toBe(true);
});
test('retries every required provider from the actual partial-publication row', async () => {
  setMockPaymentProviders({
    items: [provider('fixture-catalog')],
    discount_sync_required: true,
  });
  const original = await mockGetPackageCampaigns();
  mockGetPackageCampaigns.mockClear();
  mockGetPackageCampaigns.mockResolvedValue({
    ...original,
    items: original.items.map((item: any) => ({
      ...item,
      provider_discount_summary: {
        total: 1,
        active: 1,
        missing_provider_count: 1,
      },
    })),
  });
  await openActions();
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  );
  await waitFor(() =>
    expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenCalledWith({
      campaign_bid: 'campaign-1',
      provider: 'fixture-catalog',
    }),
  );
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'retry', provider_count: 1, outcome: 'success' },
  );
});

test('provider-reported failed publication records a failed terminal outcome', async () => {
  setMockPaymentProviders({
    items: [provider('fixture-catalog')],
    discount_sync_required: true,
  });
  mockPublishPackageCampaignProviderDiscounts.mockResolvedValue({
    items: [{ status: 'failed', failure_message: 'private provider detail' }],
  });
  await openActions();
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.publishProviderDiscounts',
    ),
  );
  await waitFor(() => expect(mockPaymentTracking).toHaveBeenCalledTimes(2));
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'publish', provider_count: 1, outcome: 'failed' },
  );
});

test('blocks overlapping publication and records one terminal result after completion', async () => {
  setMockPaymentProviders({
    items: [provider('fixture-catalog')],
    discount_sync_required: true,
  });
  let finish!: (value: unknown) => void;
  mockPublishPackageCampaignProviderDiscounts.mockReturnValue(
    new Promise(resolve => {
      finish = resolve;
    }),
  );
  await openActions();
  const publish = screen.getByText(
    'module.operationsPromotion.actions.publishProviderDiscounts',
  );
  fireEvent.click(publish);
  fireEvent.click(publish);
  expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenCalledTimes(1);
  expect(mockPaymentTracking.mock.calls).toEqual([
    [
      'admin_payment_discount_publish_start',
      { operation: 'publish', provider_count: 1 },
    ],
  ]);
  finish({ items: [] });
  await waitFor(() => expect(mockPaymentTracking).toHaveBeenCalledTimes(2));
});

test('multi-product partial publication stays partial until retry fills every provider/product pair', async () => {
  setMockPaymentProviders({
    items: [provider('stripe'), provider('fixture-catalog')],
    discount_sync_required: true,
  });
  const original = await mockGetPackageCampaigns();
  mockGetPackageCampaigns.mockClear();
  const snapshot = (missing: number) => ({
    ...original,
    items: original.items.map((item: any) => ({
      ...item,
      computed_status: 'inactive',
      enabled: false,
      product_count: 2,
      provider_discount_summary: {
        total: missing ? 3 : 4,
        active: missing ? 3 : 4,
        missing_provider_count: missing,
      },
    })),
  });
  mockGetPackageCampaigns
    .mockResolvedValueOnce(snapshot(1))
    .mockResolvedValue(snapshot(0));
  await openActions();
  expect(
    screen.getByText(
      'module.operationsPromotion.packageCampaign.providerDiscountPartial',
    ),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.actions.enable',
    }),
  );
  expect(mockUpdatePackageCampaignStatus).not.toHaveBeenCalled();
  expect(mockToast).toHaveBeenCalledWith({
    description:
      'module.operationsPromotion.messages.packageCampaignProviderSyncRequired',
    variant: 'destructive',
  });
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  );
  await waitFor(() =>
    expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenCalledTimes(2),
  );
  expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenNthCalledWith(1, {
    campaign_bid: 'campaign-1',
    provider: 'stripe',
  });
  expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenNthCalledWith(2, {
    campaign_bid: 'campaign-1',
    provider: 'fixture-catalog',
  });
  expect(
    await screen.findByText(
      'module.operationsPromotion.packageCampaign.providerDiscountActive',
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.actions.enable',
    }),
  );
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.actions.confirmEnable',
    }),
  );
  await waitFor(() =>
    expect(mockUpdatePackageCampaignStatus).toHaveBeenCalledWith({
      campaign_bid: 'campaign-1',
      enabled: true,
    }),
  );
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'retry', provider_count: 2, outcome: 'success' },
  );
});

test('failed retry retains the partial state and a later retry can complete it', async () => {
  setMockPaymentProviders({
    items: [provider('stripe'), provider('fixture-catalog')],
    discount_sync_required: true,
  });
  const original = await mockGetPackageCampaigns();
  mockGetPackageCampaigns.mockClear();
  const snapshot = (missing: number) => ({
    ...original,
    items: original.items.map((item: any) => ({
      ...item,
      product_count: 2,
      provider_discount_summary: {
        total: missing ? 3 : 4,
        active: missing ? 3 : 4,
        missing_provider_count: missing,
      },
    })),
  });
  mockGetPackageCampaigns
    .mockResolvedValueOnce(snapshot(1))
    .mockResolvedValueOnce(snapshot(1))
    .mockResolvedValue(snapshot(0));
  mockRetryPackageCampaignProviderDiscounts.mockRejectedValueOnce(
    new Error('temporary provider failure'),
  );
  await openActions();
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  );
  await waitFor(() => expect(mockGetPackageCampaigns).toHaveBeenCalledTimes(2));
  expect(
    screen.getByText(
      'module.operationsPromotion.packageCampaign.providerDiscountPartial',
    ),
  ).toBeInTheDocument();
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'retry', provider_count: 2, outcome: 'failed' },
  );
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  );
  await waitFor(() =>
    expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenCalledTimes(4),
  );
  expect(
    await screen.findByText(
      'module.operationsPromotion.packageCampaign.providerDiscountActive',
    ),
  ).toBeInTheDocument();
  expect(mockPaymentTracking).toHaveBeenLastCalledWith(
    'admin_payment_discount_publish_result',
    { operation: 'retry', provider_count: 2, outcome: 'success' },
  );
});

test.each([true, false])(
  'uses current readiness instead of historical coupon totals: %s',
  complete => {
    const item = {
      benefit_type: 'discount',
      product_count: 1,
      provider_discount_summary: {
        total: 2,
        active: 1,
        failed: 1,
        open_provider_coupon_count: 1,
        current_sync: {
          complete,
          total: complete ? 1 : 0,
          active: complete ? 1 : 0,
          missing_provider_count: complete ? 0 : 1,
        },
      },
    } as any;
    expect(isPackageCampaignProviderDiscountSynced(item)).toBe(complete);
    expect(shouldShowPackageCampaignProviderRetry(item)).toBe(!complete);
    expect(resolvePackageCampaignProviderDiscountLabel(key => key, item)).toBe(
      complete
        ? 'packageCampaign.providerDiscountActive'
        : 'packageCampaign.providerDiscountPartial',
    );
    expect(shouldShowPackageCampaignProviderRetire(item)).toBe(true);
  },
);

test.each(['stripe', 'fixture-catalog'])(
  'stale scope blocks enable until %s retry repairs current coverage',
  async activeProvider => {
    setMockPaymentProviders({
      items: [provider(activeProvider)],
      discount_sync_required: true,
    });
    const original = await mockGetPackageCampaigns();
    mockGetPackageCampaigns.mockClear();
    const snapshot = (complete: boolean) => ({
      ...original,
      items: original.items.map((item: any) => ({
        ...item,
        computed_status: 'inactive',
        enabled: false,
        provider_discount_summary: {
          total: 2,
          active: 2,
          open_provider_coupon_count: 2,
          current_sync: {
            complete,
            total: complete ? 1 : 0,
            active: complete ? 1 : 0,
            missing_provider_count: complete ? 0 : 1,
          },
        },
      })),
    });
    mockGetPackageCampaigns
      .mockResolvedValueOnce(snapshot(false))
      .mockResolvedValue(snapshot(true));
    mockRetryPackageCampaignProviderDiscounts.mockResolvedValue({
      items: [
        { status: 'failed', failure_message: 'old inactive account' },
        { status: 'active' },
      ],
      summary: snapshot(true).items[0].provider_discount_summary,
    });
    await openActions();
    expect(
      screen.getByText(
        'module.operationsPromotion.packageCampaign.providerDiscountPartial',
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    );
    expect(mockUpdatePackageCampaignStatus).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByText(
        'module.operationsPromotion.actions.retryProviderDiscounts',
      ),
    );
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith({
        description:
          'module.operationsPromotion.messages.packageCampaignProviderRetried',
      }),
    );
    expect(mockRetryPackageCampaignProviderDiscounts).toHaveBeenCalledWith({
      campaign_bid: 'campaign-1',
      provider: activeProvider,
    });
    expect(
      screen.getByText(
        'module.operationsPromotion.packageCampaign.providerDiscountActive',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsPromotion.actions.retryProviderDiscounts',
      ),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmEnable',
      }),
    );
    await waitFor(() =>
      expect(mockUpdatePackageCampaignStatus).toHaveBeenCalledWith({
        campaign_bid: 'campaign-1',
        enabled: true,
      }),
    );
    expect(mockPaymentTracking).toHaveBeenLastCalledWith(
      'admin_payment_discount_publish_result',
      { operation: 'retry', provider_count: 1, outcome: 'success' },
    );
  },
);

test('a historical disabled-channel failure cannot block enabling the healthy current channel', async () => {
  setMockPaymentProviders({
    items: [provider('stripe')],
    discount_sync_required: true,
  });
  const original = await mockGetPackageCampaigns();
  mockGetPackageCampaigns.mockClear();
  mockGetPackageCampaigns.mockResolvedValue({
    ...original,
    items: original.items.map((item: any) => ({
      ...item,
      computed_status: 'inactive',
      enabled: false,
      provider_discount_summary: {
        total: 2,
        active: 1,
        failed: 1,
        current_sync: {
          complete: true,
          total: 1,
          active: 1,
          missing_provider_count: 0,
        },
      },
    })),
  });
  await openActions();
  expect(
    screen.getByText(
      'module.operationsPromotion.packageCampaign.providerDiscountActive',
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(
      'module.operationsPromotion.actions.retryProviderDiscounts',
    ),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.actions.enable',
    }),
  );
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsPromotion.actions.confirmEnable',
    }),
  );
  await waitFor(() =>
    expect(mockUpdatePackageCampaignStatus).toHaveBeenCalledWith({
      campaign_bid: 'campaign-1',
      enabled: true,
    }),
  );
});

test('an incomplete current result reports failure even when historical coupons are active', async () => {
  setMockPaymentProviders({
    items: [provider('stripe')],
    discount_sync_required: true,
  });
  mockPublishPackageCampaignProviderDiscounts.mockResolvedValue({
    items: [{ status: 'active' }],
    summary: {
      current_sync: {
        complete: false,
        total: 0,
        active: 0,
        missing_provider_count: 1,
      },
    },
  });
  await openActions();
  fireEvent.click(
    screen.getByText(
      'module.operationsPromotion.actions.publishProviderDiscounts',
    ),
  );
  await waitFor(() =>
    expect(mockPaymentTracking).toHaveBeenLastCalledWith(
      'admin_payment_discount_publish_result',
      { operation: 'publish', provider_count: 1, outcome: 'failed' },
    ),
  );
  expect(mockToast).toHaveBeenCalledWith({
    description:
      'module.operationsPromotion.messages.packageCampaignProviderAttention',
    variant: 'destructive',
  });
});
