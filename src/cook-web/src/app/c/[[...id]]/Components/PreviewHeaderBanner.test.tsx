import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { getLearnerProfile } from '@/c-api/user';
import { LEARNER_PROFILE_CHANGED_EVENT } from '@/lib/learnerProfileEvents';
import PreviewHeaderBanner from './PreviewHeaderBanner';

let mockPreviewUserInfo: { user_id: string } | null = null;
const mockPreviewUserStoreListeners = new Set<() => void>();
const mockSetPreviewUserScope = (userId: string | null) => {
  mockPreviewUserInfo = userId ? { user_id: userId } : null;
  mockPreviewUserStoreListeners.forEach(listener => listener());
};

jest.mock('@/c-api/user', () => ({
  getLearnerProfile: jest.fn(),
}));

jest.mock('react-i18next', () => ({
  Trans: ({
    i18nKey,
    components,
  }: {
    i18nKey: string;
    components: { editLink: React.ReactElement };
  }) => (
    <>
      <span>{i18nKey}</span>
      {React.cloneElement(components.editLink, {}, 'Edit course')}
    </>
  ),
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/store/useUserStore', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  return {
    useUserStore: (
      selector: (state: { userInfo: { user_id: string } | null }) => unknown,
    ) =>
      ReactModule.useSyncExternalStore(
        listener => {
          mockPreviewUserStoreListeners.add(listener);
          return () => mockPreviewUserStoreListeners.delete(listener);
        },
        () => selector({ userInfo: mockPreviewUserInfo }),
        () => selector({ userInfo: mockPreviewUserInfo }),
      ),
  };
});

const mockGetLearnerProfile = getLearnerProfile as jest.Mock;

describe('PreviewHeaderBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSetPreviewUserScope('preview-user-a');
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '',
      learner_profile_updated_at: null,
      max_length: 1000,
    });
  });

  afterEach(async () => {
    await act(async () => {
      mockSetPreviewUserScope(null);
    });
  });

  test('discloses that the current user learning profile is active', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      learner_profile: '画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    });

    render(<PreviewHeaderBanner courseId='course-1' />);

    expect(
      await screen.findByText('module.preview.previewModeBannerWithProfile'),
    ).toBeInTheDocument();
  });

  test('discloses when preview has no learning profile', async () => {
    render(<PreviewHeaderBanner courseId='course-1' />);

    expect(
      await screen.findByText('module.preview.previewModeBannerWithoutProfile'),
    ).toBeInTheDocument();
  });

  test('refreshes the disclosure after the learner profile changes', async () => {
    mockGetLearnerProfile
      .mockResolvedValueOnce({
        learner_profile: '画像',
        learner_profile_updated_at: null,
        max_length: 1000,
      })
      .mockResolvedValueOnce({
        learner_profile: '',
        learner_profile_updated_at: null,
        max_length: 1000,
      });

    render(<PreviewHeaderBanner courseId='course-1' />);
    await screen.findByText('module.preview.previewModeBannerWithProfile');

    act(() => {
      window.dispatchEvent(new Event(LEARNER_PROFILE_CHANGED_EVENT));
    });

    expect(
      await screen.findByText('module.preview.previewModeBannerWithoutProfile'),
    ).toBeInTheDocument();
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);
  });

  test('reloads for a new account and discards the previous account response', async () => {
    let resolveFirstProfile: (value: {
      learner_profile: string;
      learner_profile_updated_at: null;
      max_length: number;
    }) => void = () => undefined;
    mockGetLearnerProfile
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveFirstProfile = resolve;
          }),
      )
      .mockResolvedValueOnce({
        learner_profile: '',
        learner_profile_updated_at: null,
        max_length: 1000,
      });

    render(<PreviewHeaderBanner courseId='course-1' />);
    await waitFor(() => expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1));
    act(() => {
      mockSetPreviewUserScope('preview-user-b');
    });
    expect(
      await screen.findByText('module.preview.previewModeBannerWithoutProfile'),
    ).toBeInTheDocument();

    await act(async () => {
      resolveFirstProfile({
        learner_profile: '账号 A 的画像',
        learner_profile_updated_at: null,
        max_length: 1000,
      });
    });
    expect(
      screen.getByText('module.preview.previewModeBannerWithoutProfile'),
    ).toBeInTheDocument();
  });

  test('links the draft notice to the current lesson editor in the same tab', async () => {
    render(
      <PreviewHeaderBanner
        courseId='course-1'
        lessonId='lesson-2'
      />,
    );

    await screen.findByText('module.preview.previewModeBannerWithoutProfile');
    const editLink = screen.getByRole('link', { name: 'Edit course' });
    expect(editLink).toHaveAttribute(
      'href',
      '/shifu/course-1?lessonid=lesson-2',
    );
    expect(editLink).not.toHaveAttribute('target');
  });

  test('omits the lesson query when no current lesson is available', async () => {
    render(<PreviewHeaderBanner courseId='course-1' />);

    await screen.findByText('module.preview.previewModeBannerWithoutProfile');
    expect(screen.getByRole('link', { name: 'Edit course' })).toHaveAttribute(
      'href',
      '/shifu/course-1',
    );
  });
});
