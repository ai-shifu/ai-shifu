import request from '@/lib/request';

export type LearnerProfile = {
  learner_profile: string;
  learner_profile_updated_at: string | null;
  has_learner_profile: boolean;
  max_length: number;
};

export const getLearnerProfile = (): Promise<LearnerProfile> => {
  return request.get('/api/user/learner-profile');
};

export const updateLearnerProfile = (
  learnerProfile: string,
): Promise<LearnerProfile> => {
  return request.put('/api/user/learner-profile', {
    learner_profile: learnerProfile,
  });
};

export const clearLearnerProfile = (): Promise<LearnerProfile> => {
  return request.delete('/api/user/learner-profile');
};
