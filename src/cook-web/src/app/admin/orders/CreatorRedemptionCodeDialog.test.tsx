import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import CreatorRedemptionCodeDialog from './CreatorRedemptionCodeDialog';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOrderShifus: jest.fn(),
    createCreatorCourseRedemptionCode: jest.fn(),
    updateCreatorCourseRedemptionCode: jest.fn(),
  },
}));

const translationCache = new Map<string, (key: string) => string>();
jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string) => {
    const cacheKey = namespace || 'translation';
    if (!translationCache.has(cacheKey)) {
      translationCache.set(cacheKey, (key: string) =>
        namespace ? `${namespace}.${key}` : key,
      );
    }
    return { t: translationCache.get(cacheKey)! };
  },
}));

jest.mock('@/hooks/useToast', () => ({
  showDefaultToast: jest.fn(),
  showErrorToast: jest.fn(),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const SelectContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: '',
    onValueChange: () => undefined,
  });

  return {
    __esModule: true,
    Select: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectValue: ({ placeholder }: { placeholder?: string }) => (
      <span>{placeholder}</span>
    ),
    SelectContent: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectItem: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(SelectContext);
      return (
        <button
          type='button'
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
  };
});

jest.mock('@/app/admin/operations/promotions/PromotionDateTimePicker', () => ({
  __esModule: true,
  default: ({
    placeholder,
    onChange,
  }: {
    placeholder: string;
    onChange: (value: string) => void;
  }) => (
    <input
      aria-label={placeholder}
      onChange={event => onChange(event.target.value)}
    />
  ),
}));

const mockGetAdminOrderShifus = api.getAdminOrderShifus as jest.Mock;
const mockCreateCreatorCourseRedemptionCode =
  api.createCreatorCourseRedemptionCode as jest.Mock;
const mockUpdateCreatorCourseRedemptionCode =
  api.updateCreatorCourseRedemptionCode as jest.Mock;

describe('CreatorRedemptionCodeDialog', () => {
  beforeEach(() => {
    mockGetAdminOrderShifus.mockReset();
    mockCreateCreatorCourseRedemptionCode.mockReset();
    mockUpdateCreatorCourseRedemptionCode.mockReset();
    mockGetAdminOrderShifus.mockResolvedValue({
      items: [{ bid: 'course-1', name: 'Course 1' }],
    });
    mockCreateCreatorCourseRedemptionCode.mockResolvedValue({
      coupon_bid: 'coupon-1',
    });
    mockUpdateCreatorCourseRedemptionCode.mockResolvedValue({
      coupon_bid: 'coupon-1',
    });
  });

  test('loads published courses and submits a course scoped redemption code', async () => {
    render(
      <CreatorRedemptionCodeDialog
        open
        onOpenChange={jest.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOrderShifus).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 100,
        published: true,
      });
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsPromotion.filters.namePlaceholder',
      ),
      { target: { value: 'Creator Batch' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.usageType.singleUse',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.discountType.fixed',
      }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsPromotion.coupon.valueAmountPlaceholder',
      ),
      { target: { value: '20' } },
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsPromotion.coupon.quantityPlaceholder',
      ),
      { target: { value: '3' } },
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Course 1' }));
    fireEvent.change(
      screen.getByLabelText('module.operationsPromotion.coupon.startAt'),
      { target: { value: '2026-04-24 10:00:00' } },
    );
    fireEvent.change(
      screen.getByLabelText('module.operationsPromotion.coupon.endAt'),
      { target: { value: '2026-05-24 10:00:00' } },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmCreate',
      }),
    );

    await waitFor(() => {
      expect(mockCreateCreatorCourseRedemptionCode).toHaveBeenCalledWith(
        expect.objectContaining({
          code: '',
          discount_type: '701',
          enabled: true,
          name: 'Creator Batch',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          start_at: '2026-04-24 10:00:00',
          end_at: '2026-05-24 10:00:00',
          total_count: '3',
          usage_type: '802',
          value: '20',
        }),
      );
    });
  });

  test('updates an existing redemption code without changing locked strategy fields', async () => {
    render(
      <CreatorRedemptionCodeDialog
        open
        onOpenChange={jest.fn()}
        coupon={{
          coupon_bid: 'coupon-1',
          name: 'Old Batch',
          code: 'OLD-CODE',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Course 1',
          start_at: '2026-04-24 10:00:00',
          end_at: '2026-05-24 10:00:00',
          total_count: 3,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24 10:00:00',
          updated_at: '2026-04-24 10:00:00',
        }}
      />,
    );

    expect(
      screen.getAllByText('module.order.redemptionCodes.editDialogTitle')
        .length,
    ).toBeGreaterThan(0);

    fireEvent.change(screen.getByDisplayValue('Old Batch'), {
      target: { value: 'Updated Batch' },
    });
    fireEvent.change(screen.getByDisplayValue('3'), { target: { value: '5' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmUpdate',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateCreatorCourseRedemptionCode).toHaveBeenCalledWith(
        expect.objectContaining({
          coupon_bid: 'coupon-1',
          code: 'OLD-CODE',
          discount_type: '701',
          name: 'Updated Batch',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          total_count: '5',
          usage_type: '801',
          value: '20',
        }),
      );
    });
    expect(mockCreateCreatorCourseRedemptionCode).not.toHaveBeenCalled();
  });

  test('locks the selected course when opened from a course card shortcut', async () => {
    render(
      <CreatorRedemptionCodeDialog
        open
        onOpenChange={jest.fn()}
        initialShifuBid='course-1'
        initialShifuName='Course 1'
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOrderShifus).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 100,
        published: true,
      });
    });

    expect(screen.getByDisplayValue('Course 1')).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: 'Course 1' }),
    ).not.toBeInTheDocument();
  });

  test('stops loading courses when the safety page limit is reached', async () => {
    mockGetAdminOrderShifus.mockResolvedValue({
      items: Array.from({ length: 100 }, (_, index) => ({
        bid: `course-${index}`,
        name: `Course ${index}`,
      })),
    });

    render(
      <CreatorRedemptionCodeDialog
        open
        onOpenChange={jest.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOrderShifus).toHaveBeenCalledTimes(50);
    });
    expect(
      await screen.findByText('module.order.redemptionCodes.tooManyCourses'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Course 0' }),
    ).toBeInTheDocument();
  });
});
