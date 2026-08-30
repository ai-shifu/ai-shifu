import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { recordCourseVisit } from '@/c-api/course';
import {
  resolveCourseVisitRecording,
  useCourseVisitRecording,
} from './courseVisitRecording';

jest.mock('@/c-api/course', () => ({
  recordCourseVisit: jest.fn(),
}));

const mockRecordCourseVisit = recordCourseVisit as jest.Mock;

const eligibleParams = {
  initialized: true,
  isLoggedIn: true,
  previewMode: false,
  urlPreviewMode: false,
  routeCourseId: 'course-1',
  loadedCourseId: 'course-1',
  userId: 'user-1',
};

const createDeferred = () => {
  let resolve!: (value?: unknown) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

function RecordingHarness({
  renderLabel,
  ...params
}: typeof eligibleParams & { renderLabel: string }) {
  useCourseVisitRecording(params);
  return <div>{renderLabel}</div>;
}

describe('course visit recording eligibility', () => {
  test.each([
    ['user initialization is pending', { initialized: false }],
    ['the account is not registered', { isLoggedIn: false }],
    ['the page is a preview', { previewMode: true }],
    ['the URL is already in preview', { urlPreviewMode: true }],
    ['the loaded course is stale', { loadedCourseId: 'course-old' }],
    ['the loaded course is absent', { loadedCourseId: null }],
    ['the registered user id is absent', { userId: '' }],
  ])('skips when %s', (_caseName, overrides) => {
    expect(
      resolveCourseVisitRecording({ ...eligibleParams, ...overrides }),
    ).toBeNull();
  });

  test('accepts a loaded live course for an initialized registered user', () => {
    expect(resolveCourseVisitRecording(eligibleParams)).toEqual({
      key: 'user-1:course-1',
      courseId: 'course-1',
    });
  });
});

describe('useCourseVisitRecording', () => {
  beforeEach(() => {
    mockRecordCourseVisit.mockReset();
    mockRecordCourseVisit.mockResolvedValue({ recorded: true });
  });

  test('records once across same-mount rerenders', async () => {
    const { rerender } = render(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='first render'
      />,
    );

    await waitFor(() => expect(mockRecordCourseVisit).toHaveBeenCalledTimes(1));

    rerender(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='second render'
      />,
    );

    expect(screen.getByText('second render')).toBeInTheDocument();
    expect(mockRecordCourseVisit).toHaveBeenCalledTimes(1);
  });

  test('reuses an in-flight request across rerenders', async () => {
    const request = createDeferred();
    mockRecordCourseVisit.mockReturnValue(request.promise);
    const { rerender } = render(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='first render'
      />,
    );

    rerender(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='second render'
      />,
    );

    expect(mockRecordCourseVisit).toHaveBeenCalledTimes(1);
    await act(async () => {
      request.resolve({ recorded: true });
      await request.promise;
    });
  });

  test('swallows failure, avoids rerender storms, and retries after remount', async () => {
    mockRecordCourseVisit
      .mockRejectedValueOnce(new Error('visit unavailable'))
      .mockResolvedValueOnce({ recorded: true });
    const firstMount = render(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='course remains visible'
      />,
    );

    expect(screen.getByText('course remains visible')).toBeInTheDocument();
    await waitFor(() => expect(mockRecordCourseVisit).toHaveBeenCalledTimes(1));

    firstMount.rerender(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='retry render'
      />,
    );

    expect(screen.getByText('retry render')).toBeInTheDocument();
    expect(mockRecordCourseVisit).toHaveBeenCalledTimes(1);

    firstMount.unmount();
    render(
      <RecordingHarness
        {...eligibleParams}
        renderLabel='new mount retry'
      />,
    );

    expect(screen.getByText('new mount retry')).toBeInTheDocument();
    await waitFor(() => expect(mockRecordCourseVisit).toHaveBeenCalledTimes(2));
  });
});
