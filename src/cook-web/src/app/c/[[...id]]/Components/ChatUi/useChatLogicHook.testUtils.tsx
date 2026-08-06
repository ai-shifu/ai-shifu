import React from 'react';
import { AppContext } from '../AppContext';
import type { SSE_INPUT_TYPE } from '@/c-api/studyV2';
import type { UseChatSessionParams } from './useChatLogicHook.types';

type Listener = (event?: Event) => void;

export class MockRunSource {
  readyState = 0;

  private listeners = new Map<string, Listener[]>();

  addEventListener = jest.fn((type: string, listener: Listener) => {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  });

  close = jest.fn(() => {
    this.readyState = 2;
    this.emit('readystatechange');
  });

  emit(type: string, event?: Event) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

export type ActiveRun = {
  source: MockRunSource;
  onMessage: (response: unknown) => Promise<void> | void;
  onError: (error: unknown) => void;
};

const buildAppContextWrapper = (mobileStyle: boolean) => {
  const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <AppContext.Provider
      value={{
        isLoggedIn: false,
        mobileStyle,
        userInfo: null,
        theme: 'light',
        frameLayout: 0,
      }}
    >
      {children}
    </AppContext.Provider>
  );
  Wrapper.displayName = mobileStyle
    ? 'MobileChatHookWrapper'
    : 'ChatHookWrapper';
  return Wrapper;
};

export const wrapper = buildAppContextWrapper(false);
export const mobileWrapper = buildAppContextWrapper(true);

export const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(next => {
    resolve = next;
  });
  return { promise, resolve };
};

export const buildBaseParams = (): UseChatSessionParams => ({
  shifuBid: 'shifu-1',
  outlineBid: 'lesson-1',
  lessonId: 'lesson-1',
  lessonHasContentUpdate: false,
  trackEvent: jest.fn(),
  trackTrailProgress: jest.fn(),
  lessonUpdate: jest.fn(),
  chapterUpdate: jest.fn(),
  updateSelectedLesson: jest.fn(),
  getNextLessonId: jest.fn(() => null),
  scrollToLesson: jest.fn(),
  showOutputInProgressToast: jest.fn(),
  onPayModalOpen: jest.fn(),
  onGoChapter: jest.fn(),
});

export type RunRequestBody = {
  input: string | Record<string, unknown>;
  input_type: SSE_INPUT_TYPE;
};
