import * as learnerProfileApi from '@/api/learnerProfile';
import {
  completeProfileOnboarding,
  createProfileOnboardingSession,
  getProfileOnboarding,
  isProfileOnboardingV2Status,
  runProfileOnboardingSession,
  skipProfileOnboarding,
} from './user';

jest.mock('@/lib/profileOnboardingSse', () => ({
  streamProfileOnboardingRuntime: jest.fn(),
}));

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: { getState: jest.fn(() => ({})) },
}));

describe('legacy c-api learner-profile adapter', () => {
  test('re-exports the modern implementation without duplicate request paths', () => {
    expect(getProfileOnboarding).toBe(learnerProfileApi.getProfileOnboardingV2);
    expect(completeProfileOnboarding).toBe(
      learnerProfileApi.completeGuidedProfileOnboarding,
    );
    expect(skipProfileOnboarding).toBe(
      learnerProfileApi.skipGuidedProfileOnboarding,
    );
    expect(createProfileOnboardingSession).toBe(
      learnerProfileApi.createProfileOnboardingSession,
    );
    expect(runProfileOnboardingSession).toBe(
      learnerProfileApi.runProfileOnboardingSession,
    );
    expect(isProfileOnboardingV2Status).toBe(
      learnerProfileApi.isProfileOnboardingV2Status,
    );
  });
});
