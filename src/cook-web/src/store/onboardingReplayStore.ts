import { create } from 'zustand';
import type { CreatorOnboardingSceneKey } from '@/types/onboarding';

type ReplayScenes = Record<CreatorOnboardingSceneKey, boolean>;

const STORAGE_KEY = 'onboarding-replay-scenes';

// localStorage (not sessionStorage) so a replay requested in the admin tab is
// visible when the course editor opens in a separate browser tab. Each scene is
// cleared once replayed, so the flag never lingers beyond the next visit.
const isStorageAvailable =
  typeof window !== 'undefined' && typeof localStorage !== 'undefined';

const EMPTY_SCENES: ReplayScenes = {
  admin_home_onboarding: false,
  course_editor_onboarding: false,
};

const readScenes = (): ReplayScenes => {
  if (!isStorageAvailable) {
    return EMPTY_SCENES;
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return EMPTY_SCENES;
    }
    const parsed = JSON.parse(raw);
    return {
      admin_home_onboarding: Boolean(parsed?.admin_home_onboarding),
      course_editor_onboarding: Boolean(parsed?.course_editor_onboarding),
    };
  } catch {
    return EMPTY_SCENES;
  }
};

const writeScenes = (scenes: ReplayScenes) => {
  if (!isStorageAvailable) {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(scenes));
  } catch {
    // Ignore storage write failures (private mode / quota exceeded).
  }
};

type OnboardingReplayState = {
  replayScenes: ReplayScenes;
  requestReplayAll: () => void;
  clearReplay: (scene: CreatorOnboardingSceneKey) => void;
};

export const useOnboardingReplayStore = create<OnboardingReplayState>(set => ({
  replayScenes: readScenes(),
  requestReplayAll: () => {
    const next: ReplayScenes = {
      admin_home_onboarding: true,
      course_editor_onboarding: true,
    };
    writeScenes(next);
    set({ replayScenes: next });
  },
  clearReplay: scene =>
    set(state => {
      const next: ReplayScenes = { ...state.replayScenes, [scene]: false };
      writeScenes(next);
      return { replayScenes: next };
    }),
}));
