import React, { useEffect } from 'react';
import { act, render } from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import { useSystemStore } from '@/c-store/useSystemStore';

jest.mock('@/c-api/course', () => ({
  getCourseInfo: jest.fn(),
}));

jest.mock('@/store', () => {
  const initUser = jest.fn();
  return {
    __esModule: true,
    UserProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    useUserStore: () => ({
      userInfo: null,
      initUser,
    }),
  };
});

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    changeLanguage: jest.fn(),
    t: (key: string) => key,
    language: 'en-US',
    resolvedLanguage: 'en-US',
  },
  browserLanguage: 'en-US',
  normalizeLanguage: () => 'en-US',
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: {
      language: 'en-US',
      changeLanguage: jest.fn(),
    },
  }),
}));

describe('C preview layout', () => {
  const originalHref = window.location.href;

  afterEach(() => {
    window.location.href = originalHref;
    act(() => {
      useSystemStore.setState({ previewMode: false, skip: false });
    });
  });

  test('applies preview mode before child effects run', async () => {
    window.location.href = 'http://localhost:3000/c/123?preview=true';
    act(() => {
      useSystemStore.setState({ previewMode: false, skip: false });
    });

    let observedPreviewMode: boolean | null = null;

    function Probe() {
      const previewMode = useSystemStore(state => state.previewMode);
      useEffect(() => {
        observedPreviewMode = previewMode;
      }, []);
      return null;
    }

    render(
      <ChatLayout>
        <Probe />
      </ChatLayout>,
    );

    await act(async () => {});
    expect(observedPreviewMode).toBe(true);
  });
});
