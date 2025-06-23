import styles from './AskButtonInner.module.scss';

import { memo, useEffect, useState, useCallback } from 'react';
import clsx from 'clsx';

import { useTranslation } from 'react-i18next';
import askIcon from '@/c-assets/newchat/light/svg-ask-16.svg';

import { animate } from 'animejs';

const ANIME_DURATION = 400;

const PERCENT_MIN = 0.00001;
const PERCENT_MAX = 99.99999;

const PERCENT_THRESHOLD_MIN = 0;
const PERCENT_THRESHOLD_MAX = 100;

const calculateAngle = (percent) => {
  return (percent / 100) * 360;
};

const calculateArcPoint = (angleInDegrees) => {
  const radians = angleInDegrees * (Math.PI / 180);
  const x = 76;
  const y = 76;
  const r = 64;

  const x1 = x + Math.sin(radians) * r;
  const y1 = y - Math.cos(radians) * r;

  return { x: x1, y: y1 };
};

const AskButtonInner = ({
  className = '',
  percent = PERCENT_THRESHOLD_MIN,
  disabled = false,
  grayColor = false,
  onClick = () => {},
}) => {
  const [endPoint, setEndPoint] = useState({ x: 0, y: 0 });
  const [largeArcFlag, setLargeArcFlag] = useState(1);
  const { t, i18n } = useTranslation('translation', { keyPrefix: 'c'});
  const [oldPercent, setOldPercent] = useState(null);

  const onButtonClick = useCallback( () => {
    if (!disabled) {
      onClick();
    }
  }, [disabled, onClick]);

  const updateRealPercent = useCallback((percent) => {
    setEndPoint(calculateArcPoint(calculateAngle(formatPercentForAnime(percent))));
    setLargeArcFlag(calculateAngle(formatPercentForAnime(percent)) < 180 ? 1 : 0);
  }, []);

  const formatPercentForAnime = (percent) => {
    return percent <= PERCENT_THRESHOLD_MIN ? PERCENT_MIN : percent >= PERCENT_THRESHOLD_MAX ? PERCENT_MAX : percent;
  };

  useEffect(() => {
    const animatePercentChange = (start, end) => {
      // TODO: FIXME
      // animate({
      //   easing: 'easeOutQuad',
      //   duration: ANIME_DURATION,
      //   update: (anim) => {
      //     if (parseInt(anim.progress) % 5 === 0) {
      //       const newPercent = start + (end - start) * (anim.progress / 100);
      //       updateRealPercent(newPercent);
      //     }
      //   },
      //   complete: () => {
      //     setOldPercent(percent);
      //   },
      // });
    };

    if (oldPercent === null) {
      updateRealPercent(percent);
      setOldPercent(percent);
    } else {
      const start = formatPercentForAnime(oldPercent);
      const end = formatPercentForAnime(percent);

      if (start !== end) {
        animatePercentChange(start, end);
        return;
      }
    }
  }, [oldPercent, percent, updateRealPercent]);

  return (
    <>
      <div
        className={clsx(styles.askButton, className)}
        onClick={onButtonClick}
      >
        <svg width="76" height="76" viewBox="0 0 152 152">
          <circle cx="76" cy="76" r="64" fill="#E2E2E2" />
          <>
            <path
              className={clsx(styles.glow)}
              id="sector"
              d={`M76,76 L76,12 A64,64 0 ${largeArcFlag},0 ${endPoint.x},${endPoint.y} Z`}
              fill="#8d9fe6"
            />
          </>
          <circle
            cx="76"
            cy="76"
            r="50"
            fill={`${grayColor || disabled ? '#BEBEBE' : '#0034D2'} `}
          />
        </svg>

        <div className={styles.askButtonInner}>
          <img src={askIcon.src} alt="ask" className={styles.askButtonIcon} />
          <div
            className={clsx(
              styles.askButtonText,
              i18n.language &&
                (i18n.language.includes('cn') || i18n.language.includes('CN'))
                ? styles.chinese
                : ''
            )}
          >
            {t('chat.ask')}
          </div>
        </div>
      </div>
    </>
  );
};

export default memo(AskButtonInner);
