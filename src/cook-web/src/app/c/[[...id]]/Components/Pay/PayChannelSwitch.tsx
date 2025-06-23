import { memo } from 'react';
import styles from './PayChannelSwitch.module.scss';
import { PAY_CHANNEL_WECHAT, PAY_CHANNEL_ZHIFUBAO } from './constans';
import classNames from 'classnames';

import payZhifubo0 from '@/c-assets/newchat/pay-zhifubao-0-2x.png';
import payZhifubo1 from '@/c-assets/newchat/pay-zhifubao-1-2x.png';
import payWechat0 from '@/c-assets/newchat/pay-wechat-0-2x.png';
import payWechat1 from '@/c-assets/newchat/pay-wechat-1-2x.png';
import { useTranslation } from 'react-i18next';

export const PayChannelSwitchItem = memo(
  ({
    channel,
    icon,
    iconSelected,
    text,
    selected,
    onClick = ({ channel }) => {},
  }) => {
    const _onClick = () => {
      onClick?.({ channel });
    }
    return (
      <div className={classNames(styles.channelSwitchItem, selected && styles.selected) } onClick={_onClick}>
        <img className={styles.channelIcon} src={selected ? iconSelected : icon} alt={text} />
        <div className={styles.channelText}>{text}</div>
      </div>
    );
  }
);
PayChannelSwitchItem.displayName = 'PayChannelSwitchItem';

export const PayChannelSwitch = ({
  channel = PAY_CHANNEL_WECHAT,
  onChange = ({ channel }) => {},
}) => {
  const {t} = useTranslation();
  return (
    <div className={styles.channelSwitch}>
      <PayChannelSwitchItem
        channel={PAY_CHANNEL_WECHAT}
        icon={payWechat0}
        iconSelected={payWechat1}
        text={t('pay.payChannelWechat')}
        selected={channel === PAY_CHANNEL_WECHAT}
        onClick={onChange}
      />
      <PayChannelSwitchItem
        channel={PAY_CHANNEL_ZHIFUBAO}
        icon={payZhifubo0}
        iconSelected={payZhifubo1}
        text={t('pay.payChannelAlipay')}
        selected={channel === PAY_CHANNEL_ZHIFUBAO}
        onClick={onChange}
      />
    </div>
  );
};

export default memo(PayChannelSwitch);
