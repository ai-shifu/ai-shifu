import { SSE } from 'sse.js';
import {
  clearPendingRequestLanguage,
  setPendingRequestLanguage,
} from '@/lib/request-language';
import { getRunMessage, streamGeneratedBlockAudio } from './studyV2';
import { attachSseBusinessResponseFallback } from '@/lib/request';

jest.mock('sse.js', () => ({
  SSE: jest.fn().mockImplementation(() => ({
    addEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
    stream: jest.fn(),
  })),
}));

jest.mock('@/lib/request', () => {
  const { getPendingRequestLanguage } = jest.requireActual(
    '@/lib/request-language',
  );
  const getCurrentRequestLanguage = () => getPendingRequestLanguage();
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
    },
    attachSseBusinessResponseFallback: jest.fn(),
    getCurrentRequestLanguage,
    getCurrentLanguageHeaders: (language?: string) => {
      const currentLanguage = language || getCurrentRequestLanguage();
      return currentLanguage ? { 'Accept-Language': currentLanguage } : {};
    },
  };
});

jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: jest.fn(headers => ({
    headers,
    requestId: 'request-id',
    harnessRunId: undefined,
  })),
}));

jest.mock('@/c-utils/envUtils', () => ({
  getResolvedBaseURL: jest.fn(() => 'https://api.example.com'),
}));

jest.mock('@/store/useUserStore', () => ({
  useUserStore: {
    getState: jest.fn(() => ({
      getToken: jest.fn(() => ''),
    })),
  },
}));

describe('getRunMessage language snapshot', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    clearPendingRequestLanguage();
  });

  test('puts the pending interface language in both the run payload and header', () => {
    setPendingRequestLanguage('fr-FR');

    const source = getRunMessage(
      'course-1',
      'lesson-1',
      false,
      { input: 'hello' },
      'learner',
      jest.fn(),
    );

    expect(SSE).toHaveBeenCalledTimes(1);
    const [url, options] = (SSE as unknown as jest.Mock).mock.calls[0];
    expect(url).toBe(
      'https://api.example.com/api/learn/shifu/course-1/run/lesson-1?preview_mode=false',
    );
    expect(options.headers).toEqual(
      expect.objectContaining({
        'Accept-Language': 'fr-FR',
        'Content-Type': 'application/json',
      }),
    );
    expect(JSON.parse(options.payload)).toEqual({
      input: { input: ['hello'] },
      language: 'fr-FR',
      listen: false,
    });
    expect(source.stream).toHaveBeenCalledTimes(1);
    expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
      source,
      expect.objectContaining({
        meta: expect.objectContaining({
          creditInsufficientAudience: 'learner',
        }),
      }),
    );
  });

  test.each(['teacher', 'teacher-collaborator'] as const)(
    'passes the explicit %s audience to preview runs',
    audience => {
      const source = getRunMessage(
        'course-1',
        'lesson-1',
        true,
        { input: 'hello' },
        audience,
        jest.fn(),
      );

      expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
        source,
        expect.objectContaining({
          meta: expect.objectContaining({
            creditInsufficientAudience: audience,
          }),
        }),
      );
    },
  );

  test('keeps an explicit request language as the immutable run snapshot', () => {
    getRunMessage(
      'course-1',
      'lesson-1',
      false,
      { input: {}, language: 'zh-CN' },
      'learner',
      jest.fn(),
    );

    const [, options] = (SSE as unknown as jest.Mock).mock.calls[0];
    expect(options.headers['Accept-Language']).toBe('zh-CN');
    expect(JSON.parse(options.payload).language).toBe('zh-CN');
  });

  test('falls back from whitespace-only body language to one request snapshot', () => {
    setPendingRequestLanguage('fr-FR');

    getRunMessage(
      'course-1',
      'lesson-1',
      false,
      { input: {}, language: ' \t ' },
      'learner',
      jest.fn(),
    );

    const [, options] = (SSE as unknown as jest.Mock).mock.calls[0];
    expect(options.headers['Accept-Language']).toBe('fr-FR');
    expect(JSON.parse(options.payload).language).toBe('fr-FR');
  });

  test.each([
    [false, 'learner'],
    [true, 'teacher'],
  ] as const)(
    'marks generated-block TTS preview=%s with the %s audience',
    (previewMode, audience) => {
      const source = streamGeneratedBlockAudio({
        shifu_bid: 'course-1',
        generated_block_bid: 'block-1',
        preview_mode: previewMode,
        creditInsufficientAudience: audience,
        onMessage: jest.fn(),
      });

      expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
        source,
        expect.objectContaining({
          meta: expect.objectContaining({
            creditInsufficientAudience: audience,
          }),
        }),
      );
    },
  );
});
