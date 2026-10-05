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
  mockTrack.mockClear();
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
it('hides the control outside rollout and records unavailability', async () => {
  jest
    .mocked(getRetakePolicy)
    .mockResolvedValue({ available: false, configured: false, limit: null });
  const { container } = render(<RetakeSettingsSection courseId='course' />);
  await act(async () => {});
  expect(container.textContent).toBe('');
  expect(mockTrack.mock.calls).toEqual([
    [
      'teacher_retake_policy_loaded',
      { shifu_bid: 'course', result: 'unavailable' },
    ],
  ]);
});

it('does not configure on load or editing, and shows saved state only after success', async () => {
  jest
    .mocked(getRetakePolicy)
    .mockResolvedValue({ available: true, configured: false, limit: null });
  jest
    .mocked(setRetakePolicy)
    .mockResolvedValue({ available: true, configured: true, limit: 2 });
  render(<RetakeSettingsSection courseId='course' />);
  await screen.findByText('module.lesson.retake.notConfigured');
  fireEvent.change(screen.getByLabelText('module.lesson.retake.settingTitle'), {
    target: { value: '2' },
  });
  expect(setRetakePolicy).not.toHaveBeenCalled();
  expect(screen.getByText('module.lesson.retake.notConfigured')).toBeTruthy();
  fireEvent.click(screen.getByText('module.lesson.retake.save'));
  await screen.findByText('module.lesson.retake.saved');
  expect(screen.queryByText('module.lesson.retake.notConfigured')).toBeNull();
  expect(screen.getByText('module.lesson.retake.currentLimit')).toBeTruthy();
  expect(setRetakePolicy).toHaveBeenCalledWith('course', 2);
});

it('makes load failure visible without exposing its text or allowing a save', async () => {
  jest.mocked(getRetakePolicy).mockRejectedValue(new Error('PRIVATE details'));
  render(<RetakeSettingsSection courseId='course' />);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.lesson.retake.policyLoadFailed',
  );
  expect(screen.queryByText('module.lesson.retake.save')).toBeNull();
  expect(mockTrack.mock.calls).toEqual([
    ['teacher_retake_policy_loaded', { shifu_bid: 'course', result: 'failed' }],
  ]);
  expect(JSON.stringify(mockTrack.mock.calls)).not.toContain('PRIVATE');
});

it('emits one safe load event despite rerenders and ignores stale loads', async () => {
  let resolveOld!: (v: any) => void;
  jest.mocked(getRetakePolicy).mockReturnValueOnce(
    new Promise(resolve => {
      resolveOld = resolve;
    }),
  );
  const view = render(<RetakeSettingsSection courseId='old' />);
  view.rerender(<RetakeSettingsSection courseId='new' />);
  await screen.findByLabelText('module.lesson.retake.settingTitle');
  await act(async () =>
    resolveOld({ available: true, configured: true, limit: 99 }),
  );
  view.rerender(<RetakeSettingsSection courseId='new' />);
  expect(mockTrack.mock.calls).toEqual([
    ['teacher_retake_policy_loaded', { shifu_bid: 'new', result: 'available' }],
  ]);
  expect(
    screen.getByLabelText('module.lesson.retake.settingTitle'),
  ).toHaveValue('2');
});
