import type {
  BillingOrderStatus,
  BillingOrderType,
  BillingProvider,
} from '@/types/billing';

type LooseString = string & {};

export type OperationCreditOrderKind = 'plan' | 'topup' | 'other' | LooseString;

export type AdminOperationCreditOrderItem = {
  bill_order_bid: string;
  creator_bid: string;
  creator_identify: string;
  creator_mobile: string;
  creator_email: string;
  creator_nickname: string;
  credit_order_kind: OperationCreditOrderKind;
  product_bid: string;
  product_code: string;
  product_type: string;
  product_name_key: string;
  credit_amount: number;
  valid_from: string | null;
  valid_to: string | null;
  order_type: BillingOrderType | LooseString;
  status: BillingOrderStatus | LooseString;
  payment_provider: BillingProvider | LooseString;
  payment_channel: string;
  payable_amount: number;
  paid_amount: number;
  currency: string;
  provider_reference_id: string;
  failure_code: string;
  failure_message: string;
  created_at: string;
  paid_at: string | null;
  failed_at: string | null;
  refunded_at: string | null;
  has_attention: boolean;
};

export type AdminOperationCreditOrderGrant = {
  granted_credits: number;
  valid_from: string | null;
  valid_to: string | null;
  source_type: string;
  source_bid: string;
};

export type AdminOperationCreditOrderListResponse = {
  items: AdminOperationCreditOrderItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationCreditOrderDetailResponse = {
  order: AdminOperationCreditOrderItem;
  metadata: Record<string, unknown> | null;
  grant: AdminOperationCreditOrderGrant | null;
};
