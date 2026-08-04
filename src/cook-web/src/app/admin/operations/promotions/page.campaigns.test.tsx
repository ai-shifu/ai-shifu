import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  mockGetCampaignDetail,
  mockGetCampaignRedemptions,
  mockGetCampaigns,
  mockGetCoupons,
  mockToast,
  mockUpdateCampaignStatus,
} from './promotionsTestUtils.test-support';
import AdminOperationPromotionsPage from './page';

describe('AdminOperationPromotionsPage campaigns', () => {
  test('shows operator-focused campaign columns and opens order list dialog from applied order count', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    expect(
      screen.getByPlaceholderText(
        'module.operationsPromotion.filters.campaignNamePlaceholder',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.operationsPromotion.campaign.applyTypeEvent')
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('app')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.viewOrders: Early Bird',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignRedemptions).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
        page_index: 1,
        page_size: 20,
      });
    });

    expect(mockGetCampaignDetail).not.toHaveBeenCalled();
    expect(
      await screen.findByText(
        'module.operationsPromotion.campaign.redemptions',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('order-2')).toBeInTheDocument();
  });
  test('shows toast when campaign redemptions request fails', async () => {
    mockGetCampaignRedemptions.mockRejectedValueOnce(
      new Error('redemptions failed'),
    );

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.viewOrders: Early Bird',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'redemptions failed',
        variant: 'destructive',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsPromotion.messages.emptyRedemptions',
      ),
    ).toBeInTheDocument();
  });
  test('only keeps apply type conditional and locks channel/value in campaign edit dialog', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-1',
          name: 'Early Bird',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: false,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-1',
        name: 'Early Bird',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: false,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
      });
    });

    expect(await screen.findByDisplayValue('Early Bird')).not.toBeDisabled();
    expect(screen.getByDisplayValue('Launch campaign')).not.toBeDisabled();
    const startAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.campaign.startAtPlaceholder',
    });
    const endAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.campaign.endAtPlaceholder',
    });
    expect(startAtButtons.at(-1)).not.toBeDisabled();
    expect(endAtButtons.at(-1)).not.toBeDisabled();

    expect(screen.getByDisplayValue('course-2')).toBeDisabled();
    expect(screen.getByDisplayValue('app')).toBeDisabled();
    expect(screen.getByDisplayValue('15')).toBeDisabled();
    expect(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.campaign.applyTypeEvent',
        })
        .at(-1),
    ).not.toBeDisabled();
  });
  test('locks campaign apply type when redemptions exist but applied order count is zero', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-voided',
          name: 'Voided Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: true,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-voided',
        name: 'Voided Campaign',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: true,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Voided Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-voided',
      });
    });

    const applyTypeButtons = await screen.findAllByRole('button', {
      name: 'module.operationsPromotion.campaign.applyTypeEvent',
    });
    expect(applyTypeButtons.at(-1)).toBeDisabled();
  });
  test('uses detail payload to refresh campaign edit locks when list data is stale', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-stale',
          name: 'Stale Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: false,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-stale',
        name: 'Stale Campaign',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: true,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Stale Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-stale',
      });
    });

    const staleApplyTypeButtons = await screen.findAllByRole('button', {
      name: 'module.operationsPromotion.campaign.applyTypeEvent',
    });
    expect(staleApplyTypeButtons.at(-1)).toBeDisabled();
  });
  test('shows toast when campaign status update is rejected', async () => {
    mockUpdateCampaignStatus.mockRejectedValueOnce(new Error('status failed'));

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmDisable',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'status failed',
        variant: 'destructive',
      });
    });
  });
  test('shows specific success toast when campaign is disabled', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmDisable',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateCampaignStatus).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
        enabled: false,
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      description:
        'module.operationsPromotion.messages.campaignDisabledSuccess',
    });
  });
  test('does not update campaign status when disable confirmation is canceled', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.cancel',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateCampaignStatus).not.toHaveBeenCalled();
    });
  });
  test('hides campaign enable action when inactive campaign is already ended', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 2,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '30',
      },
      items: [
        {
          promo_bid: 'promo-ended',
          name: 'Ended Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2026-04-01T10:00:00Z',
          end_at: '2026-04-02T10:00:00Z',
          computed_status: 'inactive',
          computed_status_key: 'module.operationsPromotion.status.inactive',
          applied_order_count: 2,
          has_redemptions: true,
          total_discount_amount: '30',
          created_at: '2026-04-01T10:00:00Z',
          updated_at: '2026-04-02T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Ended Campaign');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    ).not.toBeInTheDocument();
  });
});
