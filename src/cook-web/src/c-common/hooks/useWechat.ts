/* global WeixinJSBridge */
import { inWechat } from '@/c-constants/uiConstants';

export const useWechat = () => {
  const jsBridegetReady = Promise.resolve((resolve, reject) => {
    if (!inWechat()) {
      reject('not in wechat');
    }
    function onBridgeReady() {
      resolve();
    }
    // @ts-expect-error EXPECT
    if (typeof WeixinJSBridge == "undefined") {
      if (document.addEventListener) {
        document.addEventListener('WeixinJSBridgeReady', onBridgeReady, false);
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

  const runInJsBridge = (callback) => {
    if (!inWechat()) {
      return;
    }

    jsBridegetReady.then(callback);
  };

  const payByJsApi = async (payData) => {
    return new Promise((resolve, reject) => {
      runInJsBridge(() => {
          // @ts-expect-error EXPECT
          WeixinJSBridge.invoke(
            'getBrandWCPayRequest',
            payData,
            function (res) {
              if (res.err_msg === 'get_brand_wcpay_request:ok') {
                // @ts-expect-error EXPECT
                resolve();
              } else {
                reject(res.err_msg);
              }
            }
          );
      });
    });
  };

  return { runInJsBridge, payByJsApi };
};
