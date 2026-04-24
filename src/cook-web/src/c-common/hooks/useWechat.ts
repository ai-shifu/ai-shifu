/* global WeixinJSBridge */
import { inWechat } from '@/c-constants/uiConstants';

let jsBridgeReadyPromise: Promise<void> | null = null;

function removeBridgeReadyListener(listener: () => void) {
  if (document.removeEventListener) {
    document.removeEventListener('WeixinJSBridgeReady', listener, false);
  }
  // @ts-expect-error EXPECT
  if (document.detachEvent) {
    // @ts-expect-error EXPECT
    document.detachEvent('WeixinJSBridgeReady', listener);
    // @ts-expect-error EXPECT
    document.detachEvent('onWeixinJSBridgeReady', listener);
  }
}

export const useWechat = () => {
  const ensureJsBridgeReady = () => {
    if (!inWechat()) {
      return Promise.reject(new Error('not in wechat'));
    }
    if (jsBridgeReadyPromise) {
      return jsBridgeReadyPromise;
    }

    jsBridgeReadyPromise = new Promise<void>(resolve => {
      const onBridgeReady = () => {
        removeBridgeReadyListener(onBridgeReady);
        resolve();
      };
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

    return jsBridgeReadyPromise;
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
          WeixinJSBridge.invoke(
            'getBrandWCPayRequest',
            payData,
            function (res) {
              if (res.err_msg === 'get_brand_wcpay_request:ok') {
                resolve();
              } else {
                reject(res.err_msg);
              }
            },
          );
        }),
    );
  };

  return { runInJsBridge, payByJsApi };
};
