import request from '@/lib/request';

// Create order
export const initOrder = course_id => {
  return request.post('/api/order/init-order', { course_id });
};

// Retrieve payment URL
export const getPayUrl = ({ channel, orderId }) => {
  return request.post('/api/order/reqiure-to-pay', {
    channel,
    order_id: orderId,
  });
};

// Query order status
export const queryOrder = ({ orderId }) => {
  return request.post('/api/order/query-order', { order_id: orderId });
};

// Apply discount code
export const applyDiscountCode = ({ orderId, code }) => {
  return request.post('/api/order/apply-discount', {
    discount_code: code,
    order_id: orderId,
  });
};

// generate active order
export const initActiveOrder = ({ recordId, action, courseId }) => {
  return request.post('/api/click2cash/generate-active-order', {
    course_id: courseId,
    action,
    record_id: recordId,
  });
};
