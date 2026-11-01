import request from '@/lib/request';

/**
 * Submit feedback
 */
export const submitFeedback = feedback => {
  return request.post('/api/user/submit-feedback', { feedback });
};
