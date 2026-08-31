import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  MOCK_DIALOG_CLOSE_LABEL,
  mockGetCouponCodes,
  mockGetCouponDetail,
  mockGetCouponUsages,
  mockGetCoupons,
  mockToast,
  mockUpdateCouponStatus,
} from './promotionsTestUtils.test-support';
import AdminOperationPromotionsPage from './page';

describe('AdminOperationPromotionsPage coupons', () => {
  test('shows specific success toast when coupon is disabled', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

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
      expect(mockUpdateCouponStatus).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
        enabled: false,
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      description: 'module.operationsPromotion.messages.couponDisabledSuccess',
    });
  });
  test('does not update coupon status when disable confirmation is canceled', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

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
      expect(mockUpdateCouponStatus).not.toHaveBeenCalled();
    });
  });
  test('hides coupon enable action when inactive batch is already expired', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 3,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-expired',
          name: 'Expired Coupon',
          code: 'EXPIRED',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-01T10:00:00Z',
          end_at: '2026-04-02T10:00:00Z',
          total_count: 10,
          used_count: 3,
          computed_status: 'inactive',
          computed_status_key: 'module.operationsPromotion.status.inactive',
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

    await screen.findByText('Expired Coupon');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    ).not.toBeInTheDocument();
  });
  test('supports clearable coupon keyword input and expanding filters', async () => {
    render(<AdminOperationPromotionsPage />);

    const keywordInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.filters.keywordPlaceholder',
    );

    fireEvent.change(keywordInput, { target: { value: 'SPRING2026' } });
    expect(keywordInput).toHaveValue('SPRING2026');

    fireEvent.click(screen.getByRole('button', { name: 'common.core.close' }));
    expect(keywordInput).toHaveValue('');

    fireEvent.click(
      screen.getByRole('button', { name: /common\.core\.expand/i }),
    );

    expect(
      screen.getAllByPlaceholderText(
        'module.operationsPromotion.filters.courseQueryPlaceholder',
      ).length,
    ).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );
    await screen.findByText('Early Bird');
    expect(
      screen.getAllByPlaceholderText(
        'module.operationsPromotion.filters.courseQueryPlaceholder',
      ).length,
    ).toBeGreaterThan(0);
  });
  test('shows only used-up attention badge when an active coupon is both used up and expiring soon', async () => {
    const soonEndAt = new Date(
      Date.now() + 2 * 24 * 60 * 60 * 1000,
    ).toISOString();
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 10,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-used-up-soon',
          name: 'Soon Exhausted Coupon',
          code: 'SOONUSED',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: soonEndAt,
          total_count: 10,
          used_count: 10,
          ops_states: ['used_up', 'expiring_soon'],
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Soon Exhausted Coupon');

    expect(
      screen.getByText('module.operationsPromotion.opsState.usedUp'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsPromotion.opsState.expiringSoon'),
    ).not.toBeInTheDocument();
  });
  test('does not show coupon attention badges when the coupon is not active', async () => {
    const soonEndAt = new Date(
      Date.now() + 2 * 24 * 60 * 60 * 1000,
    ).toISOString();
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 2,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-not-started',
          name: 'Upcoming Coupon',
          code: 'UPCOMING',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
          end_at: soonEndAt,
          total_count: 10,
          used_count: 0,
          ops_states: ['expiring_soon'],
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
        {
          coupon_bid: 'coupon-inactive',
          name: 'Inactive Coupon',
          code: 'INACTIVE',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: soonEndAt,
          total_count: 10,
          used_count: 10,
          ops_states: ['used_up', 'expiring_soon'],
          computed_status: 'inactive',
          computed_status_key: 'module.operationsPromotion.status.inactive',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 2,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Upcoming Coupon');
    await screen.findByText('Inactive Coupon');

    expect(
      screen.queryByText('module.operationsPromotion.opsState.usedUp'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsPromotion.opsState.expiringSoon'),
    ).not.toBeInTheDocument();
  });
  test('does not show coupon attention badges when an active coupon has no ops states', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-stable',
          name: 'Stable Coupon',
          code: 'STABLE',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-08-24T10:00:00Z',
          total_count: 10,
          used_count: 1,
          ops_states: [],
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Stable Coupon');

    expect(
      screen.queryByText('module.operationsPromotion.opsState.usedUp'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsPromotion.opsState.expiringSoon'),
    ).not.toBeInTheDocument();
  });
  test('only keeps name quantity and active time editable in coupon edit dialog', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponDetail).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
      });
    });

    expect(await screen.findByDisplayValue('Spring Batch')).not.toBeDisabled();
    expect(screen.getByDisplayValue('10')).not.toBeDisabled();
    const startAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.coupon.startAt',
    });
    const endAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.coupon.endAt',
    });
    expect(startAtButtons.at(-1)).not.toBeDisabled();
    expect(endAtButtons.at(-1)).not.toBeDisabled();

    expect(screen.getByDisplayValue('SPRING2026')).toBeDisabled();
    expect(screen.getByDisplayValue('20')).toBeDisabled();
    expect(screen.getByDisplayValue('course-1')).toBeDisabled();
  });
  test('uses coupon detail payload to refresh stale edit values before opening dialog', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 3,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-stale',
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
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponDetail.mockResolvedValueOnce({
      coupon: {
        coupon_bid: 'coupon-stale',
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
        total_count: 20,
        used_count: 8,
        computed_status: 'active',
        computed_status_key: 'module.operationsPromotion.status.active',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-25T11:00:00Z',
      },
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponDetail).toHaveBeenCalledWith({
        coupon_bid: 'coupon-stale',
      });
    });

    const quantityInput = (await screen.findAllByDisplayValue('20')).find(
      element => !element.hasAttribute('disabled'),
    );
    expect(quantityInput).toBeDefined();
  });
  test('shows toast when coupon detail request fails', async () => {
    mockGetCouponDetail.mockRejectedValueOnce(new Error('detail failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'detail failed',
        variant: 'destructive',
      });
    });

    expect(screen.queryByDisplayValue('Spring Batch')).not.toBeInTheDocument();
  });
  test('clears course id when coupon scope switches to all courses', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    );

    const courseInput = screen
      .getAllByPlaceholderText(
        'module.operationsPromotion.filters.courseIdPlaceholder',
      )
      .at(-1)!;
    fireEvent.change(courseInput, { target: { value: 'course-123' } });
    expect(courseInput).toHaveValue('course-123');

    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.scope.allCourses',
        })
        .at(-1)!,
    );

    expect(courseInput).toHaveValue('');
  });
  test('hides generic code input for single-use coupon', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    );

    const codeInputCountBefore = screen.getAllByPlaceholderText(
      'module.operationsPromotion.coupon.codePlaceholder',
    ).length;
    expect(codeInputCountBefore).toBeGreaterThan(0);

    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.usageType.singleUse',
        })
        .at(-1)!,
    );

    expect(
      screen.queryAllByPlaceholderText(
        'module.operationsPromotion.coupon.codePlaceholder',
      ),
    ).toHaveLength(codeInputCountBefore - 1);
  });
  test('does not render coupon detail action in coupon operations', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    expect(
      screen.queryByText('module.operationsPromotion.coupon.codes'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.viewDetail',
      }),
    ).not.toBeInTheDocument();
  });
  test('shows placeholder in codes entry column for generic coupon', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    ).not.toBeInTheDocument();
  });
  test('opens sub-code dialog from codes entry column for single-use coupon', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockResolvedValueOnce({
      items: [
        {
          coupon_usage_bid: 'usage-1',
          code: 'CODE001',
          status: 902,
          status_key: 'module.order.couponStatus.active',
          user_bid: '',
          user_mobile: '',
          user_email: '',
          user_nickname: '',
          order_bid: '',
          used_at: '',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: '',
      });
    });

    expect(
      screen.getByText('module.operationsPromotion.coupon.codes'),
    ).toBeInTheDocument();
    expect(screen.getByText('CODE001')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.coupon.subCode'),
    ).toBeInTheDocument();
  });
  test('shows toast when coupon codes request fails', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: '',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockRejectedValueOnce(new Error('codes failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'codes failed',
        variant: 'destructive',
      });
    });

    expect(
      await screen.findByText('module.operationsPromotion.messages.emptyCodes'),
    ).toBeInTheDocument();
  });
  test('supports sub-code keyword search in codes dialog', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            coupon_usage_bid: 'usage-1',
            code: 'CODE001',
            status: 902,
            status_key: 'module.order.couponStatus.active',
            user_bid: '',
            user_mobile: '',
            user_email: '',
            user_nickname: '',
            order_bid: '',
            used_at: '',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 1,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    const searchInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.coupon.subCodePlaceholder',
    );
    fireEvent.change(searchInput, { target: { value: 'CODE001' } });
    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.actions.search',
        })
        .at(-1)!,
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenLastCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: 'CODE001',
      });
    });
  });
  test('resets coupon codes dialog search state when reopened', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: '',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    const searchInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.coupon.subCodePlaceholder',
    );
    fireEvent.change(searchInput, { target: { value: 'CODE001' } });
    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.actions.search',
        })
        .at(-1)!,
    );

    fireEvent.click(
      screen.getByRole('button', { name: MOCK_DIALOG_CLOSE_LABEL }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    expect(
      await screen.findByPlaceholderText(
        'module.operationsPromotion.coupon.subCodePlaceholder',
      ),
    ).toHaveValue('');
    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenLastCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: '',
      });
    });
  });
  test('shows toast when coupon usages request fails', async () => {
    mockGetCouponUsages.mockRejectedValueOnce(new Error('usages failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: '3/10',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'usages failed',
        variant: 'destructive',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsPromotion.messages.emptyUsages',
      ),
    ).toBeInTheDocument();
  });
  test('shows export action for single-use coupon', async () => {
    const createObjectURL = jest.fn(() => 'blob:coupon-codes');
    const revokeObjectURL = jest.fn();
    const anchorClick = jest
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    Object.defineProperty(window.URL, 'createObjectURL', {
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      writable: true,
      value: revokeObjectURL,
    });

    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockResolvedValueOnce({
      items: [
        {
          coupon_usage_bid: 'usage-1',
          code: 'CODE001',
          status: 902,
          status_key: 'module.order.couponStatus.active',
          user_bid: '',
          user_mobile: '',
          user_email: '',
          user_nickname: '',
          order_bid: '',
          used_at: '',
          updated_at: '2026-04-24T11:00:00Z',
        },
        {
          coupon_usage_bid: 'usage-2',
          code: 'CODE002',
          status: 903,
          status_key: 'module.order.couponStatus.used',
          user_bid: 'learner-1',
          user_mobile: '13812345678',
          user_email: '',
          user_nickname: 'Learner',
          order_bid: 'order-1',
          used_at: '2026-04-25T11:00:00Z',
          updated_at: '2026-04-25T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 100,
      total: 2,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.exportCodes',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 100,
      });
    });
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
    anchorClick.mockRestore();
  });
});
