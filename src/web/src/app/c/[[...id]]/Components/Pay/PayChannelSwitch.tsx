import styles from './PayChannelSwitch.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import Image, { type StaticImageData } from 'next/image';

import { PAY_CHANNEL_WECHAT, PAY_CHANNEL_ZHIFUBAO } from './constans';

import payZhifubo0 from '@/assets/newchat/pay-zhifubao-0-2x.png';
import payZhifubo1 from '@/assets/newchat/pay-zhifubao-1-2x.png';
import payWechat0 from '@/assets/newchat/pay-wechat-0-2x.png';
import payWechat1 from '@/assets/newchat/pay-wechat-1-2x.png';
import type { PaymentOption } from '@/types/payment';
import {
  resolvePaymentOption,
  paymentSelectionKey,
} from '@/lib/paymentContracts';

interface PayChannelSwitchItemProps {
  channel: string;
  icon?: StaticImageData;
  iconSelected?: StaticImageData;
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
        data-clickable='true'
        onClick={handleClick}
      >
        {icon && iconSelected ? (
          <Image
            className={styles.channelIcon}
            src={selected ? iconSelected : icon}
            alt={text}
          />
        ) : null}
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
  options?: PaymentOption[];
}

export const PayChannelSwitch = ({
  channel = PAY_CHANNEL_WECHAT,
  onChange,
  availableChannels,
  options,
}: PayChannelSwitchProps) => {
  const { t } = useTranslation();
  if (options) {
    const selectedOption = resolvePaymentOption(options, channel);
    return (
      <div className={styles.channelSwitch}>
        {options
          .filter(option => option.action === 'qr')
          .map(option => {
            const wechat = option.method === 'wechat';
            const alipay = option.method === 'alipay';
            return (
              <PayChannelSwitchItem
                key={option.id}
                channel={paymentSelectionKey(option, options)}
                icon={wechat ? payWechat0 : alipay ? payZhifubo0 : undefined}
                iconSelected={
                  wechat ? payWechat1 : alipay ? payZhifubo1 : undefined
                }
                text={t(
                  wechat
                    ? 'module.pay.payChannelWechat'
                    : alipay
                      ? 'module.pay.payChannelAlipay'
                      : option.label_key,
                )}
                selected={selectedOption?.id === option.id}
                onClick={onChange}
              />
            );
          })}
      </div>
    );
  }
  const enabledChannels =
    availableChannels == null ? null : new Set(availableChannels);
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
