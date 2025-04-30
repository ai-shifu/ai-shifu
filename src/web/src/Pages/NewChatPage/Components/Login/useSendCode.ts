import { useState, useRef } from 'react';
import { sendSmsCode } from 'Api/user';
import { memo } from 'react';

const DEFAULT_COUNTDOWN = 60;
const DEFAULT_COUNTDOWN_INTERVAL = 1000;

export const useSendCode = ({ countDownTime = DEFAULT_COUNTDOWN }) => {
  const [countDown, setCountDown] = useState(0);
  const timer = useRef();

  const sendCode = async (mobile, checkCode) => {
    if (!!countDown) {
      throw new Error(`${countDownTime}秒内只能发送一次`);
    }

    // send code logic
    await sendSmsCode({ mobile, check_code: checkCode });

    setCountDown(countDownTime);

    timer.current = setInterval(() => {
      setCountDown((countDown) => {
        if (countDown === 0) {
          clearInterval(timer.current);
          timer.current = null;
          return 0;
        }
        return countDown - 1;
      });
    }, DEFAULT_COUNTDOWN_INTERVAL);
  };

  const reset = () => {
    setCountDown(0);
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  return [countDown, sendCode, reset];
};

export default memo(useSendCode);
