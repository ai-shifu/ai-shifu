import {
  buildAdminCourseListParams,
  buildAdminCreditOrderListParams,
  buildAdminDateRangeParams,
  buildAdminLearnOrderListParams,
  buildAdminPaginationParams,
  buildAdminUserListParams,
} from './adminFilterParams';

describe('admin filter params', () => {
  it('builds pagination params without renaming the existing API fields', () => {
    expect(buildAdminPaginationParams(3, 20)).toEqual({
      page_index: 3,
      page_size: 20,
    });
  });

  it('converts date ranges to UTC params and keeps empty date filters empty', () => {
    expect(buildAdminDateRangeParams('', '')).toEqual({
      start_time: '',
      end_time: '',
    });
    expect(buildAdminDateRangeParams('2026-08-06', '2026-08-07')).toEqual({
      start_time: expect.stringMatching(/^2026-08-0[5-6]T/),
      end_time: expect.stringMatching(/^2026-08-0[7-8]T/),
    });
  });

  it('builds course list params with trimmed text filters and update date keys', () => {
    expect(
      buildAdminCourseListParams({
        pageIndex: 2,
        pageSize: 20,
        quickFilter: 'published',
        filters: {
          shifu_bid: ' course-1 ',
          course_name: ' Course ',
          creator_keyword: ' teacher@example.com ',
          course_status: 'published',
          start_time: '',
          end_time: '',
          updated_start_time: '',
          updated_end_time: '',
        },
      }),
    ).toEqual({
      page_index: 2,
      page_size: 20,
      shifu_bid: 'course-1',
      course_name: 'Course',
      creator_keyword: 'teacher@example.com',
      course_status: 'published',
      quick_filter: 'published',
      start_time: '',
      end_time: '',
      updated_start_time: '',
      updated_end_time: '',
    });
  });

  it('builds user list params with status, role, quick filter, and trimmed text filters', () => {
    expect(
      buildAdminUserListParams({
        pageIndex: 1,
        pageSize: 20,
        quickFilter: 'paid',
        filters: {
          identifier: ' user@example.com ',
          nickname: ' Alice ',
          user_status: 'paid',
          user_role: 'learner',
          start_time: '',
          end_time: '',
        },
      }),
    ).toEqual({
      page_index: 1,
      page_size: 20,
      identifier: 'user@example.com',
      nickname: 'Alice',
      user_status: 'paid',
      user_role: 'learner',
      quick_filter: 'paid',
      start_time: '',
      end_time: '',
    });
  });

  it('builds learn order params while preserving all status-like filter fields', () => {
    expect(
      buildAdminLearnOrderListParams({
        pageIndex: 4,
        pageSize: 20,
        filters: {
          user_keyword: ' learner ',
          order_bid: ' order-1 ',
          shifu_bid: ' course-1 ',
          course_name: ' Course ',
          status: '502',
          order_source: 'direct',
          payment_channel: 'wechatpay',
          start_time: '',
          end_time: '',
        },
      }),
    ).toEqual({
      page_index: 4,
      page_size: 20,
      user_keyword: 'learner',
      order_bid: 'order-1',
      shifu_bid: 'course-1',
      course_name: 'Course',
      status: '502',
      order_source: 'direct',
      payment_channel: 'wechatpay',
      start_time: '',
      end_time: '',
    });
  });

  it('omits optional credit order flags when they are not active', () => {
    expect(
      buildAdminCreditOrderListParams({
        pageIndex: 1,
        pageSize: 20,
        filters: {
          creator_keyword: ' creator ',
          product_keyword: ' package ',
          bill_order_bid: ' ',
          credit_order_kind: '',
          status: 'paid',
          has_available_credits: false,
          payment_provider: '',
          start_time: '',
          end_time: '',
        },
      }),
    ).toEqual({
      page_index: 1,
      page_size: 20,
      creator_keyword: 'creator',
      product_keyword: 'package',
      credit_order_kind: '',
      status: 'paid',
      payment_provider: '',
      start_time: '',
      end_time: '',
    });
  });

  it('includes optional credit order flags when active', () => {
    expect(
      buildAdminCreditOrderListParams({
        pageIndex: 1,
        pageSize: 20,
        filters: {
          creator_keyword: '',
          product_keyword: '',
          bill_order_bid: ' bill-1 ',
          credit_order_kind: 'package',
          status: '',
          has_available_credits: true,
          payment_provider: 'stripe',
          start_time: '',
          end_time: '',
        },
      }),
    ).toEqual(
      expect.objectContaining({
        bill_order_bid: 'bill-1',
        has_available_credits: true,
      }),
    );
  });
});
