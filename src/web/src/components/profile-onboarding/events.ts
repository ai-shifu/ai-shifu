export const PROFILE_ONBOARDING_EVENTS = {
  SHOWN: 'profile_onboarding_shown',
  COMPLETED: 'profile_onboarding_completed',
  SKIPPED: 'profile_onboarding_skipped',
  RETENTION_SHOWN: 'profile_onboarding_retention_shown',
  RETENTION_CONTINUED: 'profile_onboarding_retention_continued',
  RETENTION_COMPLETED: 'profile_onboarding_retention_completed',
  RETENTION_DEFER_ATTEMPT: 'profile_onboarding_retention_defer_attempt',
  RETENTION_DEFER_RESULT: 'profile_onboarding_retention_defer_result',
  RUNTIME_FAILED: 'profile_onboarding_runtime_failed',
  SETTINGS_SAVED: 'learner_profile_settings_saved',
  SETTINGS_CLEARED: 'learner_profile_settings_cleared',
  SETTINGS_RERUN_STARTED: 'learner_profile_settings_rerun_started',
  COLLECTION_ROUTE_CHOSEN: 'learner_profile_collection_route_chosen',
  // AI-help funnel contract (Umami): OPENED counts each successful view entry;
  // PROMPT_COPIED counts each successful clipboard write. Report raw events and
  // distinct identified learners separately; the client does not deduplicate.
  // Population: profile collection sessions where AI help is available.
  // Payload: source + presentation only—never prompt, answer, profile, or IDs.
  // These append-only events supplement existing route/attempt/result metrics.
  ASSISTANT_OPENED: 'learner_profile_assistant_opened',
  ASSISTANT_PROMPT_COPIED: 'learner_profile_assistant_prompt_copied',
  ASSISTANT_ATTEMPT: 'learner_profile_assistant_attempt',
  ASSISTANT_RESULT: 'learner_profile_assistant_result',
} as const;
