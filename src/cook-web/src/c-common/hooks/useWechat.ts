/* global WeixinJSBridge */
import { inWechat } from '@/c-constants/uiConstants';

export const useWechat = () => {
  let jsBridegetReady: Promise<void> | null = null;

  const ensureJsBridgeReady = () => {
    if (!inWechat()) {
      return Promise.reject(new Error('not in wechat'));
    }
    if (jsBridegetReady) {
      return jsBridegetReady;
    }
    jsBridegetReady = new Promise<void>(resolve => {
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
    return jsBridegetReady;
  };

  const runInJsBridge = callback => {
    return ensureJsBridgeReady().then(callback);
  };

  const payByJsApi = async payData => {
    return new Promise((resolve, reject) => {
      runInJsBridge(() => {
        // @ts-expect-error EXPECT
        WeixinJSBridge.invoke('getBrandWCPayRequest', payData, function (res) {
          if (res.err_msg === 'get_brand_wcpay_request:ok') {
            // @ts-expect-error EXPECT
            resolve();
          } else {
            reject(res.err_msg);
          }
        });
      }).catch(reject);
    });
  };

  return { runInJsBridge, payByJsApi };
};
