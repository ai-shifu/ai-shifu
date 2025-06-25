import request from '@/c-service/Request';

/**
 * 提交反馈
 */
export const submitFeedback = (feedback) => {
  return request({
    url: '/api/user/submit-feedback',
    method: 'post',
    data: { feedback }
  });
};
