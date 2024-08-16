import request from "../Service/Request";

export const testPurchaseOrder = ({ orderId }) => {
  return request({
    url: '/api/order/order-test',
    method: 'post',
    data: { order_id: orderId }
  })
}
