import { render, screen } from '@testing-library/react';
import { RetakeAllowanceMessage } from './RetakeAllowanceMessage';
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
it.each([
  [1, true, false, 'last'],
  [0, false, false, 'exhausted'],
  [2, false, true, 'busy'],
  [3, true, false, 'remaining'],
])(
  'shows the correct limit state for %s opportunities',
  (remaining, allowed, in_progress, message) => {
    render(
      <RetakeAllowanceMessage
        loading={false}
        status={{
          available: true,
          limit: 3,
          used: 3 - Number(remaining),
          reserved: 0,
          remaining: Number(remaining),
          allowed: Boolean(allowed),
          in_progress: Boolean(in_progress),
        }}
      />,
    );
    expect(screen.getByRole('status').textContent).toBe(
      `module.lesson.retake.${message}`,
    );
  },
);
