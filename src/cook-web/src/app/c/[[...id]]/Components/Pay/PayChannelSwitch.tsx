import styles from './PayChannelSwitch.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next';

import Image from 'next/image';

import { PAY_CHANNEL_WECHAT, PAY_CHANNEL_ZHIFUBAO } from './constans';

import payZhifubo0 from '@/c-assets/newchat/pay-zhifubao-0-2x.png';
import payZhifubo1 from '@/c-assets/newchat/pay-zhifubao-1-2x.png';
import payWechat0 from '@/c-assets/newchat/pay-wechat-0-2x.png';
import payWechat1 from '@/c-assets/newchat/pay-wechat-1-2x.png';

export const PayChannelSwitchItem = memo(
  ({
    // @ts-expect-error EXPECT
    channel,
    // @ts-expect-error EXPECT
    icon,
    // @ts-expect-error EXPECT
    iconSelected,
    // @ts-expect-error EXPECT
    text,
    // @ts-expect-error EXPECT
    selected,
    // @ts-expect-error EXPECT
    onClick = ({}) => {},
  }) => {
    const _onClick = () => {
      onClick?.({ channel });
    }
    return (
      <div className={cn(styles.channelSwitchItem, selected && styles.selected) } onClick={_onClick}>
        <Image className={styles.channelIcon} src={selected ? iconSelected : icon} alt={text} />
        <div className={styles.channelText}>{text}</div>
      </div>
    );
  }
);
PayChannelSwitchItem.displayName = 'PayChannelSwitchItem';

export const PayChannelSwitch = ({
  channel = PAY_CHANNEL_WECHAT,
  onChange = () => {},
}) => {
  const {t} = useTranslation();
  return (
    <div className={styles.channelSwitch}>
      <PayChannelSwitchItem
        // @ts-expect-error EXPECT
        channel={PAY_CHANNEL_WECHAT}
        icon={payWechat0}
        iconSelected={payWechat1}
        text={t('pay.payChannelWechat')}
        selected={channel === PAY_CHANNEL_WECHAT}
        onClick={onChange}
      />
      <PayChannelSwitchItem
        // @ts-expect-error EXPECT
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
