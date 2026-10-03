import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { RetakeSettingsSection } from './RetakeSettingsSection';
import { getRetakePolicy, setRetakePolicy } from '@/api/retake';
const mockTrack = jest.fn();
jest.mock('@/api/retake', () => ({
  getRetakePolicy: jest.fn(),
  setRetakePolicy: jest.fn(),
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
beforeEach(() => {
  jest.clearAllMocks();
  mockTrack.mockReset();
  jest
    .mocked(getRetakePolicy)
    .mockResolvedValue({ available: true, configured: true, limit: 2 });
  jest
    .mocked(setRetakePolicy)
    .mockResolvedValue({ available: true, configured: true, limit: 3 });
});

it('saves a validated policy once, tracking only the terminal API result', async () => {
  let finish!: () => void;
  jest.mocked(setRetakePolicy).mockReturnValue(
    new Promise(resolve => {
      finish = () => resolve({ available: true, configured: true, limit: 3 });
    }),
  );
  render(<RetakeSettingsSection courseId='course' />);
  const input = await screen.findByLabelText(
    'module.lesson.retake.settingTitle',
  );
  fireEvent.change(input, { target: { value: '3' } });
  const save = screen.getByText('module.lesson.retake.save');
  fireEvent.click(save);
  fireEvent.click(save);
  expect(setRetakePolicy).toHaveBeenCalledTimes(1);
  expect(mockTrack).not.toHaveBeenCalled();
  await act(async () => finish());
  expect(setRetakePolicy).toHaveBeenCalledWith('course', 3);
  expect(mockTrack.mock.calls).toEqual([
    [
      'teacher_retake_policy_result',
      { shifu_bid: 'course', result: 'success', limit: 3 },
    ],
  ]);
  expect(screen.getByText('module.lesson.retake.saved')).toBeTruthy();
});
it('rejects invalid values and permits explicit unlimited', async () => {
  render(<RetakeSettingsSection courseId='course' />);
  const input = await screen.findByLabelText(
    'module.lesson.retake.settingTitle',
  );
  fireEvent.change(input, { target: { value: '-1' } });
  fireEvent.click(screen.getByText('module.lesson.retake.save'));
  expect(setRetakePolicy).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '' } });
  fireEvent.click(screen.getByText('module.lesson.retake.save'));
  await waitFor(() =>
    expect(setRetakePolicy).toHaveBeenCalledWith('course', null),
  );
});
it('preserves editing on API failure and excludes error text from analytics', async () => {
  jest.mocked(setRetakePolicy).mockRejectedValue(new Error('PRIVATE'));
  render(<RetakeSettingsSection courseId='course' />);
  await screen.findByLabelText('module.lesson.retake.settingTitle');
  fireEvent.click(screen.getByText('module.lesson.retake.save'));
  await waitFor(() =>
    expect(mockTrack).toHaveBeenCalledWith('teacher_retake_policy_result', {
      shifu_bid: 'course',
      result: 'failed',
      limit: 2,
    }),
  );
  expect(screen.queryByText('module.lesson.retake.saved')).toBeNull();
  expect(JSON.stringify(mockTrack.mock.calls)).not.toContain('PRIVATE');
});
it('does not let analytics failure hide a successful save', async () => {
  mockTrack.mockImplementation(() => {
    throw new Error('unavailable');
  });
  render(<RetakeSettingsSection courseId='course' />);
  await screen.findByLabelText('module.lesson.retake.settingTitle');
  fireEvent.click(screen.getByText('module.lesson.retake.save'));
  expect(await screen.findByText('module.lesson.retake.saved')).toBeTruthy();
});
it('hides the control outside rollout without events', async () => {
  jest
    .mocked(getRetakePolicy)
    .mockResolvedValue({ available: false, configured: false, limit: null });
  const { container } = render(<RetakeSettingsSection courseId='course' />);
  await act(async () => {});
  expect(container.textContent).toBe('');
  expect(mockTrack).not.toHaveBeenCalled();
});
