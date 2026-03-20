/* global WeixinJSBridge */
import { inWechat } from '@/c-constants/uiConstants';

export const useWechat = () => {
  let jsBridgeReady: Promise<void> | null = null;

  const ensureJsBridgeReady = () => {
    if (!inWechat()) {
      return Promise.reject(new Error('not in wechat'));
    }
    if (jsBridgeReady) {
      return jsBridgeReady;
    }
    jsBridgeReady = new Promise<void>(resolve => {
      function onBridgeReady() {
        resolve();
      }
      // @ts-expect-error EXPECT
      if (typeof WeixinJSBridge == 'undefined') {
        if (document.addEventListener) {
          document.addEventListener(
            'WeixinJSBridgeReady',
            onBridgeReady,
            false,
          );
          // @ts-expect-error EXPECT
        } else if (document.attachEvent) {
          // @ts-expect-error EXPECT
          document.attachEvent('WeixinJSBridgeReady', onBridgeReady);
          // @ts-expect-error EXPECT
          document.attachEvent('onWeixinJSBridgeReady', onBridgeReady);
        }
      } else {
        onBridgeReady();
      }
    });
    return jsBridgeReady;
  };

  const runInJsBridge = async callback => {
    await ensureJsBridgeReady();
    return callback();
  };

  const payByJsApi = async payData => {
    await runInJsBridge(
      () =>
        new Promise<void>((resolve, reject) => {
          // @ts-expect-error EXPECT
          WeixinJSBridge.invoke('getBrandWCPayRequest', payData, function (res) {
            if (res.err_msg === 'get_brand_wcpay_request:ok') {
              resolve();
            } else {
              reject(res.err_msg);
            }
          });
        }),
    );
  };

  return { runInJsBridge, payByJsApi };
};
