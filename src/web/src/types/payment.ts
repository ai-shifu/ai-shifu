/** Shared browser contracts for payment selection, execution and recovery. */
export type PaymentAction =
  | { type: 'qr'; url: string }
  | { type: 'redirect'; url: string; session_id?: string | null }
  | { type: 'jsapi'; parameters: Record<string, string> }
  | {
      type: 'sdk_confirm';
      sdk: string;
      client_secret: string;
      publishable_key?: string | null;
    }
  | { type: 'none' };

export type PaymentOption = {
  id: string;
  provider: string;
  channel: string;
  method: string;
  scene: string;
  action: PaymentAction['type'];
  billing_mode: 'platform_managed' | 'provider_managed';
  label_key: string;
  poll_provider: boolean;
  requires_open_id: boolean;
  prefer_in_wechat?: boolean;
};

export type PaymentContract = {
  payment_contract_version?: number;
  payment_action?: PaymentAction | null;
  poll_provider?: boolean;
};
