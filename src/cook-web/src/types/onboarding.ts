export type CreatorOnboardingSceneKey =
  | 'admin_home_onboarding'
  | 'course_editor_onboarding';

export type CreatorOnboardingUserSegment =
  | 'new_creator'
  | 'existing_creator_rollout'
  | 'ineligible';

export type CreatorOnboardingBillingVariant =
  | 'trial_credit'
  | 'generic_billing';

export type CreatorOnboardingSceneStatus = {
  completed: boolean;
  completed_at: string | null;
  eligible: boolean;
  variant: CreatorOnboardingBillingVariant | null;
};

export type CreatorOnboardingStatus = {
  eligible: boolean;
  user_segment: CreatorOnboardingUserSegment;
  version: string;
  scenes: Record<CreatorOnboardingSceneKey, CreatorOnboardingSceneStatus>;
  guide_course: {
    bid: string;
    title: string;
    language: string;
  };
};
