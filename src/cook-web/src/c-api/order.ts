import request from "@/lib/request";

export const testPurchaseOrder = ({ orderId }) => {
  return request.post('/api/order/order-test', { order_id: orderId });
};

// 创建订单
export const initOrder = (course_id) => {
  return request.post('/api/order/init-order', { course_id });
};

// 获取支付链接
export const getPayUrl = ({ channel, orderId }) => {
  return request.post('/api/order/reqiure-to-pay', { channel, order_id: orderId });
};

// 查询订单
export const queryOrder = ({ orderId }) => {
  return request.post('/api/order/query-order', { order_id: orderId });
};

// 使用优惠码
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
}
