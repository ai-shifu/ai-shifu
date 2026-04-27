import styles from './PayChannelSwitch.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import Image, { type StaticImageData } from 'next/image';

import { PAY_CHANNEL_WECHAT, PAY_CHANNEL_ZHIFUBAO } from './constans';

import payZhifubo0 from '@/c-assets/newchat/pay-zhifubao-0-2x.png';
import payZhifubo1 from '@/c-assets/newchat/pay-zhifubao-1-2x.png';
import payWechat0 from '@/c-assets/newchat/pay-wechat-0-2x.png';
import payWechat1 from '@/c-assets/newchat/pay-wechat-1-2x.png';

interface PayChannelSwitchItemProps {
  channel: string;
  icon: StaticImageData;
  iconSelected: StaticImageData;
  text: string;
  selected: boolean;
  onClick?: (payload: { channel: string }) => void;
}

export const PayChannelSwitchItem = memo(
  ({
    channel,
    icon,
    iconSelected,
    text,
    selected,
    onClick,
  }: PayChannelSwitchItemProps) => {
    const handleClick = () => {
      onClick?.({ channel });
    };
    return (
      <div
        className={cn(styles.channelSwitchItem, selected && styles.selected)}
        onClick={handleClick}
      >
        <Image
          className={styles.channelIcon}
          src={selected ? iconSelected : icon}
          alt={text}
        />
        <div className={styles.channelText}>{text}</div>
      </div>
    );
  },
);
PayChannelSwitchItem.displayName = 'PayChannelSwitchItem';

interface PayChannelSwitchProps {
  channel?: string;
  onChange?: (payload: { channel: string }) => void;
  availableChannels?: string[];
}

export const PayChannelSwitch = ({
  channel = PAY_CHANNEL_WECHAT,
  onChange,
  availableChannels,
}: PayChannelSwitchProps) => {
  const { t } = useTranslation();
  const enabledChannels = availableChannels?.length
    ? new Set(availableChannels)
    : null;
  return (
    <div className={styles.channelSwitch}>
      {!enabledChannels || enabledChannels.has(PAY_CHANNEL_WECHAT) ? (
        <PayChannelSwitchItem
          channel={PAY_CHANNEL_WECHAT}
          icon={payWechat0}
          iconSelected={payWechat1}
          text={t('module.pay.payChannelWechat')}
          selected={channel === PAY_CHANNEL_WECHAT}
          onClick={onChange}
        />
      ) : null}
      {!enabledChannels || enabledChannels.has(PAY_CHANNEL_ZHIFUBAO) ? (
        <PayChannelSwitchItem
          channel={PAY_CHANNEL_ZHIFUBAO}
          icon={payZhifubo0}
          iconSelected={payZhifubo1}
          text={t('module.pay.payChannelAlipay')}
          selected={channel === PAY_CHANNEL_ZHIFUBAO}
          onClick={onChange}
        />
      ) : null}
    </div>
  );
};

export default memo(PayChannelSwitch);
