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

    if (typeof WeixinJSBridge == "undefined") {
      if (document.addEventListener) {
        document.addEventListener('WeixinJSBridgeReady', onBridgeReady, false);
      } else if (document.attachEvent) {
        document.attachEvent('WeixinJSBridgeReady', onBridgeReady);
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

          WeixinJSBridge.invoke(
            'getBrandWCPayRequest',
            payData,
            function (res) {
              if (res.err_msg === 'get_brand_wcpay_request:ok') {
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
