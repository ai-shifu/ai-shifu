import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import api from '@/api';
import { ShifuProvider, useShifu } from '@/store/use-shifu';
import MinimalTreeItem from './MinimalTreeItem';

const mockTracking = jest.fn();

jest.mock('@/lib/tracking', () => ({
  EVENT_NAMES: {},
  tracking: (...args: unknown[]) => mockTracking(...args),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getShifuDetail: jest.fn(),
    getMdflow: jest.fn(),
    saveMdflow: jest.fn(),
    getProfileItemDefinitions: jest.fn(),
    getProfileVariableUsage: jest.fn(),
  },
}));

jest.mock('@/api/learning', () => ({
  LEARNING_PERMISSION: { GUEST: 'guest', TRIAL: 'trial', NORMAL: 'normal' },
}));

jest.mock('../chapter-setting', () => () => null);
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

it('retries a failed selected lesson without saving and stops retrying after recovery', async () => {
  const consoleError = jest
    .spyOn(console, 'error')
    .mockImplementation(() => {});
  try {
    const lesson = {
      id: 'lesson-1',
      bid: 'lesson-1',
      depth: 1,
      name: 'Lesson',
    };
    (api.getShifuDetail as jest.Mock).mockResolvedValue({ bid: 'course-1' });
    (api.getProfileItemDefinitions as jest.Mock).mockResolvedValue([]);
    (api.getProfileVariableUsage as jest.Mock).mockResolvedValue({});
    let rejectInitial!: (error: Error) => void;
    let resolveRetry!: (body: string) => void;
    (api.getMdflow as jest.Mock)
      .mockReturnValueOnce(
        new Promise<string>((_, reject) => {
          rejectInitial = reject;
        }),
      )
      .mockRejectedValueOnce(new Error('Retry failed'))
      .mockReturnValueOnce(
        new Promise<string>(resolve => {
          resolveRetry = resolve;
        }),
      );
    mockTracking.mockResolvedValueOnce(undefined).mockImplementationOnce(() => {
      throw new Error('Analytics unavailable');
    });

    let actions!: ReturnType<typeof useShifu>['actions'];
    function Editor() {
      const state = useShifu();
      actions = state.actions;
      return (
        <>
          <ul>
            <MinimalTreeItem
              item={lesson}
              parent={null}
              depth={1}
              indentationWidth={16}
              isLast
              isOver={false}
              isOverParent={false}
            />
          </ul>
          <output>{state.isMdflowLoaded ? state.mdflow : 'unloaded'}</output>
        </>
      );
    }

    render(
      <ShifuProvider>
        <Editor />
      </ShifuProvider>,
    );
    await act(async () => {
      await actions.loadShifu('course-1');
    });
    let initialLoad!: Promise<boolean>;
    act(() => {
      actions.setCurrentNode(lesson);
      initialLoad = actions.loadMdflow(lesson.bid, 'course-1');
    });
    const lessonRow = screen.getByText('Lesson');
    fireEvent.click(lessonRow);
    expect(api.getMdflow).toHaveBeenCalledTimes(1);
    await act(async () => {
      rejectInitial(new Error('Initial load failed'));
      await initialLoad;
    });
    expect(mockTracking).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(lessonRow);
    });
    expect(screen.getByRole('status')).toHaveTextContent('unloaded');
    expect(mockTracking).toHaveBeenCalledTimes(1);

    act(() => {
      fireEvent.click(lessonRow);
      fireEvent.click(lessonRow);
    });
    expect(api.getMdflow).toHaveBeenCalledTimes(3);
    expect(api.getMdflow).toHaveBeenLastCalledWith({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
    });
    expect(mockTracking).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveRetry('Recovered draft body');
    });

    expect(screen.getByRole('status')).toHaveTextContent(
      'Recovered draft body',
    );
    fireEvent.click(lessonRow);
    expect(api.getMdflow).toHaveBeenCalledTimes(3);
    expect(api.saveMdflow).not.toHaveBeenCalled();
    expect(mockTracking.mock.calls).toEqual([
      ['creator_lesson_load_retry_result', { outcome: 'not_applied' }],
      ['creator_lesson_load_retry_result', { outcome: 'applied' }],
    ]);
  } finally {
    consoleError.mockRestore();
  }
});
