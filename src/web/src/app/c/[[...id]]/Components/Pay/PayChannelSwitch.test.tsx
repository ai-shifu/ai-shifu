import { fireEvent, render, screen } from '@testing-library/react';
import { PayChannelSwitch } from './PayChannelSwitch';
import type { PaymentOption } from '@/types/payment';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const fixture: PaymentOption = {
  id: 'fixture-pay:fixture_qr',
  provider: 'fixture-pay',
  channel: 'fixture_qr',
  method: 'fixture-method',
  scene: 'qr',
  action: 'qr',
  billing_mode: 'platform_managed',
  label_key: 'module.pay.payChannelAlipay',
  poll_provider: true,
  requires_open_id: false,
};

test('renders and selects a server-declared QR method without a gateway whitelist', () => {
  const onChange = jest.fn();
  render(
    <PayChannelSwitch
      options={[
        fixture,
        {
          ...fixture,
          id: 'hosted',
          channel: 'hosted_checkout',
          action: 'redirect',
        },
      ]}
      channel={fixture.channel}
      onChange={onChange}
    />,
  );
  expect(screen.getAllByText(fixture.label_key)).toHaveLength(1);
  fireEvent.click(screen.getByText(fixture.label_key));
  expect(onChange).toHaveBeenCalledWith({ channel: fixture.channel });
});

test('keeps the legacy wallet choices when the server has no options contract', () => {
  render(<PayChannelSwitch />);
  expect(screen.getByText('module.pay.payChannelWechat')).toBeInTheDocument();
  expect(screen.getByText('module.pay.payChannelAlipay')).toBeInTheDocument();
});

test('an explicitly empty option list does not restore disabled legacy wallets', () => {
  render(<PayChannelSwitch options={[]} />);
  expect(
    screen.queryByText('module.pay.payChannelWechat'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText('module.pay.payChannelAlipay'),
  ).not.toBeInTheDocument();
});

test('uses the option identity when added integrations share a QR route name', () => {
  const onChange = jest.fn();
  const second = {
    ...fixture,
    id: 'second-pay:fixture_qr',
    provider: 'second-pay',
    label_key: 'module.pay.pay',
  };
  render(
    <PayChannelSwitch
      options={[fixture, second]}
      channel={fixture.id}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByText(second.label_key));
  expect(onChange).toHaveBeenCalledWith({ channel: second.id });
});
