import request from '@/lib/request';

export type LearnerProfile = {
  learner_profile: string;
  learner_profile_updated_at: string | null;
  has_learner_profile: boolean;
  max_length: number;
  nickname?: string;
  nickname_max_length?: number;
  legacy_profile_values?: Partial<
    Record<
      'sys_user_nickname' | 'sys_user_background' | 'sys_user_style',
      string
    >
  >;
};

export type OptimizedLearnerProfile = {
  optimized_learner_profile: string;
};

export const getLearnerProfile = (): Promise<LearnerProfile> => {
  return request.get('/api/user/learner-profile', { skipErrorToast: true });
};

export const updateLearnerProfile = (
  learnerProfile: string,
  nickname?: string,
): Promise<LearnerProfile> => {
  const payload: { learner_profile: string; nickname?: string } = {
    learner_profile: learnerProfile,
  };
  if (nickname !== undefined) {
    payload.nickname = nickname;
  }
  return request.put('/api/user/learner-profile', payload, {
    skipErrorToast: true,
  });
};

export const optimizeLearnerProfile = (
  learnerProfile: string,
): Promise<OptimizedLearnerProfile> => {
  return request.post(
    '/api/user/learner-profile/optimize',
    { learner_profile: learnerProfile },
    { skipErrorToast: true },
  );
};
