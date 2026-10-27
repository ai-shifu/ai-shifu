import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import PermissionRequestModal from './PermissionRequestModal';

const mockSubmitFeedback = jest.fn();
const mockToast = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/api/bz', () => ({
  submitFeedback: (...args: unknown[]) => mockSubmitFeedback(...args),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h1>{children}</h1>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

describe('PermissionRequestModal validation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSubmitFeedback.mockResolvedValue(undefined);
  });

  it.each([
    ['empty', '', 'abcde'],
    ['shorter than five characters', 'abcd', '  abcde  '],
  ])(
    'shows feedback for a request that is %s and submits after correction',
    async (_label, invalidRequest, validRequest) => {
      const onClose = jest.fn();
      render(
        <PermissionRequestModal
          open
          onClose={onClose}
        />,
      );

      const request = screen.getByRole('textbox');
      const submit = screen.getByRole('button', {
        name: 'module.permission.permission.requestSubmit',
      });

      fireEvent.change(request, { target: { value: invalidRequest } });
      // Submit directly to exercise resolver validation independently of native minLength.
      fireEvent.submit(submit.closest('form')!);

      expect(
        await screen.findByText(
          'module.permission.permission.requestPlaceholder',
        ),
      ).toBeInTheDocument();
      expect(request).toHaveAttribute('aria-invalid', 'true');
      expect(mockSubmitFeedback).not.toHaveBeenCalled();
      expect(mockToast).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.change(request, { target: { value: validRequest } });
      fireEvent.click(submit);

      await waitFor(() => {
        expect(mockSubmitFeedback).toHaveBeenCalledTimes(1);
        expect(mockSubmitFeedback).toHaveBeenCalledWith('[权限申请] abcde');
        expect(onClose).toHaveBeenCalledTimes(1);
      });
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.permission.permission.requestSuccess',
      });
      expect(request).toHaveValue('');
      expect(
        screen.queryByText('module.permission.permission.requestPlaceholder'),
      ).not.toBeInTheDocument();
    },
  );
});
