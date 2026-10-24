import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import ImportActivationDialog from './ImportActivationDialog';

const mockGetAdminOrderShifus = jest.fn();
const mockImportActivationOrder = jest.fn();
const mockToast = jest.fn();
const mockEnvState = {
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
};
const mockTranslate = (key: string) => key;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOrderShifus: (...args: unknown[]) =>
      mockGetAdminOrderShifus(...args),
    importActivationOrder: (...args: unknown[]) =>
      mockImportActivationOrder(...args),
  },
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockTranslate,
    i18n: { language: 'en-US' },
  }),
}));

describe('ImportActivationDialog validation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockGetAdminOrderShifus.mockResolvedValue({ items: [] });
    mockImportActivationOrder.mockResolvedValue({
      success: [{ mobile: '13800138000' }],
      failed: [],
    });
  });

  it('shows both required field errors without opening import confirmation', async () => {
    render(
      <ImportActivationDialog
        open
        onOpenChange={jest.fn()}
      />,
    );

    const contact = screen.getByLabelText(
      'module.order.importActivation.mobileLabel',
    );
    fireEvent.submit(contact.closest('form')!);

    expect(
      await screen.findByText('module.order.importActivation.mobileRequired'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.order.importActivation.courseRequired'),
    ).toBeInTheDocument();
    expect(contact).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockImportActivationOrder).not.toHaveBeenCalled();
  });

  it.each([
    {
      mode: 'phone',
      label: 'mobileLabel',
      required: 'mobileRequired',
      invalid: 'mobileInvalidLines',
      valid: '13800138000',
    },
    {
      mode: 'email',
      label: 'emailLabel',
      required: 'emailRequired',
      invalid: 'emailInvalidLines',
      valid: 'learner@example.test',
    },
  ])(
    'validates empty and invalid $mode contacts before allowing confirmed import',
    async ({ mode, label, required, invalid, valid }) => {
      mockEnvState.loginMethodsEnabled = [mode];
      mockEnvState.defaultLoginMethod = mode;
      const onSuccess = jest.fn();
      const onOpenChange = jest.fn();
      render(
        <ImportActivationDialog
          open
          onOpenChange={onOpenChange}
          onSuccess={onSuccess}
          initialCourseId='course-1'
          initialCourseName='Course'
        />,
      );

      const contact = screen.getByLabelText(
        `module.order.importActivation.${label}`,
      );
      const form = contact.closest('form')!;
      fireEvent.change(contact, { target: { value: '   ' } });
      fireEvent.submit(form);
      expect(
        await screen.findByText(`module.order.importActivation.${required}`),
      ).toBeInTheDocument();
      expect(mockImportActivationOrder).not.toHaveBeenCalled();

      fireEvent.change(contact, { target: { value: 'invalid contact' } });
      fireEvent.submit(form);
      expect(
        await screen.findByText(`module.order.importActivation.${invalid}`),
      ).toBeInTheDocument();
      expect(mockImportActivationOrder).not.toHaveBeenCalled();
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

      fireEvent.change(contact, { target: { value: `  ${valid}  ` } });
      fireEvent.submit(form);
      expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
      expect(mockImportActivationOrder).not.toHaveBeenCalled();
      fireEvent.click(
        screen.getByRole('button', { name: 'common.core.confirm' }),
      );

      await waitFor(() =>
        expect(mockImportActivationOrder).toHaveBeenCalledWith({
          lines: [valid],
          course_id: 'course-1',
          contact_type: mode,
        }),
      );
      expect(mockImportActivationOrder).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
      expect(onSuccess).toHaveBeenCalledWith('');
    },
  );
});
