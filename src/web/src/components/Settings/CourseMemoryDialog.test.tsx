import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { deleteCourseMemory, listCourseMemory } from '@/api/courseMemory';
import CourseMemoryDialog from './CourseMemoryDialog';

const mockTrack = jest.fn();
let mockIdentity = 0;
jest.mock('@/api/courseMemory', () => ({
  listCourseMemory: jest.fn(),
  deleteCourseMemory: jest.fn(),
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('@/lib/tracking', () => ({
  getTrackingIdentityGeneration: () => mockIdentity,
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const entry = {
  value_id: 'private-id',
  key: 'private-key',
  value: '<script>private answer</script>',
  updated_at: null,
};
const page = { items: [entry], next_before: null };
const label = (key: string) => `module.settings.${key}`;
const setup = () =>
  render(
    <CourseMemoryDialog
      courseId='course-id'
      onClose={jest.fn()}
    />,
  );
const confirm = async () => {
  await screen.findByText(entry.value);
  fireEvent.click(screen.getByRole('button', { name: label('memoryDelete') }));
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: label('memoryConfirm') }),
    );
  });
};

describe('CourseMemoryDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIdentity = 0;
    mockTrack.mockResolvedValue(undefined);
    (listCourseMemory as jest.Mock).mockResolvedValue(page);
    (deleteCourseMemory as jest.Mock).mockResolvedValue({ conflict: false });
  });

  it('shows plain text and records one eligible open even under StrictMode', async () => {
    render(
      <React.StrictMode>
        <CourseMemoryDialog
          courseId='course-id'
          onClose={jest.fn()}
        />
      </React.StrictMode>,
    );
    expect(await screen.findByText(entry.value)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(mockTrack.mock.calls).toEqual([
      ['learner_course_memory_opened', { course_id: 'course-id' }],
    ]);
  });

  it('keeps confirmation pending and single-flight, then removes the confirmed row', async () => {
    let finish!: (value: { conflict: boolean }) => void;
    (deleteCourseMemory as jest.Mock).mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        }),
    );
    const onClose = jest.fn();
    render(
      <CourseMemoryDialog
        courseId='course-id'
        onClose={onClose}
      />,
    );
    await confirm();
    const button = screen.getByRole('button', { name: label('memoryConfirm') });
    fireEvent.click(button);
    expect(button).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'common.core.cancel' }),
    ).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect(deleteCourseMemory).toHaveBeenCalledTimes(1);
    await act(async () => finish({ conflict: false }));
    await screen.findByText(label('memoryEmpty'));
    expect(mockTrack.mock.calls.slice(1)).toEqual([
      ['learner_course_memory_delete_attempt', { course_id: 'course-id' }],
      [
        'learner_course_memory_delete_result',
        { course_id: 'course-id', outcome: 'success' },
      ],
    ]);
    expect(JSON.stringify(mockTrack.mock.calls)).not.toContain('private');
  });

  it('keeps a failed deletion open and allows an explicit retry', async () => {
    (deleteCourseMemory as jest.Mock).mockRejectedValueOnce(
      new Error('private raw error'),
    );
    setup();
    await confirm();
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: label('memoryConfirm') }),
      ).toBeEnabled(),
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(
      screen.getAllByText(label('memoryDeleteFailed')).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(entry.value)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: label('memoryConfirm') }),
    );
    await screen.findByText(label('memoryEmpty'));
    expect(
      mockTrack.mock.calls.filter(
        ([name]) => name === 'learner_course_memory_delete_result',
      ),
    ).toEqual([
      [
        'learner_course_memory_delete_result',
        { course_id: 'course-id', outcome: 'failed' },
      ],
      [
        'learner_course_memory_delete_result',
        { course_id: 'course-id', outcome: 'success' },
      ],
    ]);
  });

  it('refreshes a stale selection without deleting a newer value', async () => {
    (deleteCourseMemory as jest.Mock).mockResolvedValue({ conflict: true });
    (listCourseMemory as jest.Mock)
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce({
        items: [{ ...entry, value_id: 'new-id', value: 'new value' }],
        next_before: null,
      });
    setup();
    await confirm();
    expect(await screen.findByText('new value')).toBeInTheDocument();
    expect(screen.getByText(label('memoryChanged'))).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(deleteCourseMemory).toHaveBeenCalledWith('course-id', 'private-id');
  });

  it('paginates and retries load failures', async () => {
    (listCourseMemory as jest.Mock)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ ...page, next_before: '50' })
      .mockResolvedValueOnce({
        items: [{ ...entry, value_id: 'second', value: 'second page' }],
        next_before: null,
      });
    setup();
    fireEvent.click(
      await screen.findByRole('button', { name: label('memoryRetry') }),
    );
    await screen.findByText(entry.value);
    fireEvent.click(screen.getByRole('button', { name: label('memoryMore') }));
    await screen.findByText('second page');
    expect(listCourseMemory).toHaveBeenLastCalledWith('course-id', '50');
    expect(screen.getByText(entry.value)).toBeInTheDocument();
  });

  it.each(['throws', 'rejects'])('continues when tracking %s', async mode => {
    mockTrack.mockImplementation(() => {
      if (mode === 'throws') throw new Error('offline');
      return Promise.reject(new Error('offline'));
    });
    setup();
    await confirm();
    await screen.findByText(label('memoryEmpty'));
    expect(deleteCourseMemory).toHaveBeenCalledTimes(1);
  });

  it('ignores an old identity deletion response and emits no terminal attribution', async () => {
    let finish!: (value: { conflict: boolean }) => void;
    (deleteCourseMemory as jest.Mock).mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        }),
    );
    setup();
    await confirm();
    mockIdentity++;
    await act(async () => finish({ conflict: false }));
    expect(
      mockTrack.mock.calls.filter(
        ([name]) => name === 'learner_course_memory_delete_result',
      ),
    ).toHaveLength(0);
  });

  it('does not apply pending loads after unmount', async () => {
    let finish!: (value: typeof page) => void;
    (listCourseMemory as jest.Mock).mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        }),
    );
    const view = setup();
    view.unmount();
    await act(async () => finish(page));
    expect(screen.queryByText(entry.value)).not.toBeInTheDocument();
  });
});
