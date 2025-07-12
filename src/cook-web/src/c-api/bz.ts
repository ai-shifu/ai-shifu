import request from '@/lib/request';

/**
 * 提交反馈
 */
export const submitFeedback = (feedback) => {
  return request.post('/api/user/submit-feedback', { feedback });
};
