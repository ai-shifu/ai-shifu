export const PAY_CHANNEL_WECHAT = 'wx_pub_qr';
export const PAY_CHANNEL_ZHIFUBAO = 'alipay_qr';
export const PAY_CHANNEL_WECHAT_JSAPI = 'wx_pub';

export const PAY_CHANNELS = [
  {
    type: PAY_CHANNEL_WECHAT,
    name: '微信支付',
  },
  { type: PAY_CHANNEL_ZHIFUBAO, name: '支付宝支付' },
];

export const getPayChannelOptions = () => {
  return PAY_CHANNELS.map((item) => ({
    label: item.name,
    value: item.type,
  }));
};

export const ORDER_STATUS = {
  BUY_STATUS_INIT: 501,
  BUY_STATUS_SUCCESS: 502,
  BUY_STATUS_REFUND: 503,
  BUY_STATUS_TO_BE_PAID: 504,
};
