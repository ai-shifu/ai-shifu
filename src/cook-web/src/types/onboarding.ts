export type CreatorOnboardingSceneKey =
  | 'admin_home_onboarding'
  | 'course_editor_onboarding';

export type CreatorOnboardingSceneStatus = {
  completed: boolean;
  completed_at: string | null;
};

export type CreatorOnboardingStatus = {
  eligible: boolean;
  version: string;
  scenes: Record<CreatorOnboardingSceneKey, CreatorOnboardingSceneStatus>;
  guide_course: {
    bid: string;
    title: string;
    language: string;
  };
};
