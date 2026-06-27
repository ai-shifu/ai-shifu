import { create } from 'zustand';
import type { CreatorOnboardingSceneKey } from '@/types/onboarding';

type OnboardingReplayState = {
  replayScene: CreatorOnboardingSceneKey | null;
  requestReplay: (scene: CreatorOnboardingSceneKey) => void;
  clearReplay: () => void;
};

export const useOnboardingReplayStore = create<OnboardingReplayState>(set => ({
  replayScene: null,
  requestReplay: scene => set({ replayScene: scene }),
  clearReplay: () => set({ replayScene: null }),
}));
