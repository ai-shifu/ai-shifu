import request from "../Service/Request";





export const testOrder = async (order_id) => {
    return request({
      url: "/api/order/order-test",
      method: "post",
        data: {
            order_id
        },
    });
  }
