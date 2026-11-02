import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { CouponCodeModal } from './CouponCodeModal';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('CouponCodeModal validation', () => {
  it('shows the required message for an empty code and submits after correction', async () => {
    const onOk = jest.fn().mockResolvedValue(undefined);
    const onCancel = jest.fn();
    render(
      <CouponCodeModal
        open
        onOk={onOk}
        onCancel={onCancel}
      />,
    );

    const input = screen.getByPlaceholderText('module.groupon.placeholder');
    const submit = screen.getByRole('button', { name: 'common.core.ok' });
    fireEvent.click(submit);

    expect(
      await screen.findByText('module.groupon.inputMessage'),
    ).toBeInTheDocument();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(onOk).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: 'VALID-CODE' } });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(onOk).toHaveBeenCalledTimes(1);
      expect(onOk).toHaveBeenCalledWith({ couponCode: 'VALID-CODE' });
      expect(
        screen.queryByText('module.groupon.inputMessage'),
      ).not.toBeInTheDocument();
      expect(input).toHaveAttribute('aria-invalid', 'false');
    });
  });
});
