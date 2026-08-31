import type {
  ProfileOnboardingPresentation,
  ProfileOnboardingSessionIntent,
} from '@/api/learnerProfile';

export type ProfileCollectionRoute = 'guided_questions' | 'ai_assistant';
export type ProfileAssistantFailureCategory =
  | 'stream_failed'
  | 'runtime_failed'
  | 'session_expired'
  | 'missing_result';

const buildProfileCollectionContext = ({
  intent,
  presentation,
}: {
  intent: ProfileOnboardingSessionIntent;
  presentation: ProfileOnboardingPresentation;
}) => ({
  source: intent === 'settings' ? ('settings' as const) : ('guided' as const),
  presentation,
});

export const buildProfileCollectionRouteAnalytics = ({
  intent,
  presentation,
  route,
}: {
  intent: ProfileOnboardingSessionIntent;
  presentation: ProfileOnboardingPresentation;
  route: ProfileCollectionRoute;
}) => ({
  ...buildProfileCollectionContext({ intent, presentation }),
  route,
});

export const buildProfileAssistantAttemptAnalytics = ({
  intent,
  presentation,
}: {
  intent: ProfileOnboardingSessionIntent;
  presentation: ProfileOnboardingPresentation;
}) => buildProfileCollectionContext({ intent, presentation });

export const buildProfileAssistantResultAnalytics = ({
  intent,
  presentation,
  outcome,
  failureCategory,
}: {
  intent: ProfileOnboardingSessionIntent;
  presentation: ProfileOnboardingPresentation;
  outcome: 'success' | 'failed';
  failureCategory?: ProfileAssistantFailureCategory;
}) => ({
  ...buildProfileCollectionContext({ intent, presentation }),
  outcome,
  ...(outcome === 'failed' && failureCategory
    ? { failure_category: failureCategory }
    : {}),
});
