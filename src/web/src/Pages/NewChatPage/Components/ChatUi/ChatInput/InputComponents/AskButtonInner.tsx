import { memo } from 'react';
import classNames from 'classnames';
import styles from './AskButtonInner.module.scss';
import { useTranslation } from 'react-i18next';
import askIcon from '@Assets/newchat/light/svg-ask-16.svg';
import { useCallback } from 'react';

const AskButtonInner = ({
  className = '',
  disabled = false,
  grayColor = false,
  onClick = () => {},
}) => {
  const { t, i18n } = useTranslation();

  const onButtonClick = useCallback( () => {
    if (!disabled) {
      onClick();
    }
  }, [disabled, onClick]);

  return (
    <>
      <div
        className={classNames(styles.askButton, className)}
        onClick={onButtonClick}
      >
        <svg width="76" height="76" viewBox="0 0 152 152">
          <circle
            cx="76"
            cy="76"
            r="50"
            fill={`${grayColor || disabled ? '#BEBEBE' : '#0034D2'} `}
          />
        </svg>

        <div className={styles.askButtonInner}>
          <img src={askIcon} alt="ask" className={styles.askButtonIcon} />
          <div
            className={classNames(
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
