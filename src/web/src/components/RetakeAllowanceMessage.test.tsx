import { render, screen } from '@testing-library/react';
import { RetakeAllowanceMessage } from './RetakeAllowanceMessage';
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
it.each([1, 2, 10])(
  'hides available allowance even with %s remaining',
  remaining => {
    render(
      <RetakeAllowanceMessage
        loading={false}
        status={{
          available: true,
          allowed: true,
          in_progress: false,
          remaining,
        }}
      />,
    );
    expect(screen.queryByRole('status')).toBeNull();
  },
);
it('shows no quota query reminder while loading', () => {
  render(<RetakeAllowanceMessage loading />);
  expect(screen.queryByRole('status')).toBeNull();
});
it.each([
  [false, false, 'exhausted'],
  [false, true, 'busy'],
])('shows actionable blocked state', (allowed, in_progress, message) => {
  render(
    <RetakeAllowanceMessage
      loading={false}
      status={{ available: true, allowed, in_progress }}
    />,
  );
  expect(screen.getByRole('status').textContent).toBe(
    `module.lesson.retake.${message}`,
  );
});
it('shows retry guidance on failure', () => {
  render(
    <RetakeAllowanceMessage
      loading={false}
      failed
    />,
  );
  expect(screen.getByRole('status').textContent).toBe(
    'module.lesson.retake.loadFailed',
  );
});
