import './promotionsTestUtils';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminOperationPromotionsPage from './page';
import {
  mockGetCampaigns,
  mockGetCoupons,
  mockUpdateCampaignStatus,
  mockUpdateCouponStatus,
} from './promotionsTestUtils';

describe('AdminOperationPromotionsPage list and pagination', () => {
  test('loads coupon tab by default', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => {
      expect(mockGetCoupons).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '',
        ops_state: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Spring Batch')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.table.scope'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.scope.singleCourse'),
    ).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    ).toBeInTheDocument();
  });
  test('keeps coupon page when switching away and back', async () => {
    mockGetCoupons
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-1',
            name: 'Spring Batch',
            code: 'SPRING2026',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-21',
            name: 'Page Two Coupon',
            code: 'PAGE2',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(screen.getByRole('link', { name: '2' }));

    await screen.findByText('Page Two Coupon');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );

    expect(await screen.findByText('Page Two Coupon')).toBeInTheDocument();
  });
  test('switches to campaign tab and loads campaigns', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        course_query: '',
        apply_type: '',
        channel: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Early Bird')).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
  });
  test('keeps campaign filter state aligned when switching tabs', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    const keywordInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.filters.campaignNamePlaceholder',
    );
    fireEvent.change(keywordInput, { target: { value: 'Retention' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: 'Retention',
        course_query: '',
        apply_type: '',
        channel: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });
  test('keeps campaign page when switching away and back', async () => {
    mockGetCampaigns
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-1',
            name: 'Page One Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Page One Campaign');

    fireEvent.click(screen.getByRole('link', { name: '2' }));

    await screen.findByText('Page Two Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 2,
        page_size: 20,
        keyword: '',
        course_query: '',
        apply_type: '',
        channel: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });
  test('passes coupon usage type and ops state filters to the list request', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', { name: /common\.core\.expand/i }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.usageType.singleUse',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.opsState.usedUp',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetCoupons).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '802',
        ops_state: 'used_up',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });
  test('passes campaign apply type and channel filters to the list request', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', { name: /common\.core\.expand/i }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.campaign.applyTypeEvent',
      }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsPromotion.campaign.channelPlaceholder',
      ),
      { target: { value: 'app' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        course_query: '',
        apply_type: '2102',
        channel: 'app',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });
  test('clears stale coupon list when reload fails', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    mockGetCoupons.mockRejectedValueOnce(new Error('coupon list failed'));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    expect(await screen.findByText('coupon list failed')).toBeInTheDocument();
    expect(screen.queryByText('Spring Batch')).not.toBeInTheDocument();
  });
  test('clears stale campaign list when reload fails', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    mockGetCampaigns.mockRejectedValueOnce(new Error('campaign list failed'));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    expect(await screen.findByText('campaign list failed')).toBeInTheDocument();
    expect(screen.queryByText('Early Bird')).not.toBeInTheDocument();
  });
  test('falls back to the last valid coupon page when current page becomes empty', async () => {
    mockGetCoupons
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-21',
            name: 'Page Two Coupon',
            code: 'PAGE2',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [],
        page: 2,
        page_count: 1,
        page_size: 20,
        total: 20,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-1',
            name: 'Recovered Coupon',
            code: 'RECOVER',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 20,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Page Two Coupon');

    mockUpdateCouponStatus.mockResolvedValueOnce({
      coupon_bid: 'coupon-21',
      enabled: false,
    });

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
      expect(mockGetCoupons).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '',
        ops_state: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Recovered Coupon')).toBeInTheDocument();
  });
  test('falls back to the last valid campaign page when current page becomes empty', async () => {
    mockGetCampaigns
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [],
        page: 2,
        page_count: 1,
        page_size: 20,
        total: 20,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-1',
            name: 'Recovered Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 20,
      });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Page Two Campaign');

    mockUpdateCampaignStatus.mockResolvedValueOnce({
      promo_bid: 'promo-21',
      enabled: false,
    });

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
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        course_query: '',
        apply_type: '',
        channel: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Recovered Campaign')).toBeInTheDocument();
  });
});
