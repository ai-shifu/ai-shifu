export const LEARNER_PROFILE_CHANGED_EVENT = 'learner-profile-changed';

export const notifyLearnerProfileChanged = () => {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new Event(LEARNER_PROFILE_CHANGED_EVENT));
};
