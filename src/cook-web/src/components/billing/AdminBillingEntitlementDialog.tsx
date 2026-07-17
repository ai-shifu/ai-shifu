'use client';

import React from 'react';
import { ChevronDown, ImagePlus } from 'lucide-react';
import { useSWRConfig } from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import type {
  AdminBillingCustomizationDraft,
  AdminBillingEntitlementGrantPayload,
  AdminBillingEntitlementItem,
  BillingCustomization,
  BillingDomainBinding,
  BillingCustomizationProvider,
} from '@/types/billing';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import {
  setAdminBillingConfigStatusState,
  type AdminBillingConfigStatus,
  type AdminBillingConfigStatusRecord,
  resolveAdminBillingCreatorPrimary,
} from './AdminBillingShared';

type AdminBillingEntitlementDialogProps = {
  open: boolean;
  initialItem?: AdminBillingEntitlementItem | null;
  initialConfigRecord?: AdminBillingConfigStatusRecord | null;
  onOpenChange: (open: boolean) => void;
};

const ENTITLEMENT_FIELDS = [
  'branding_enabled',
  'custom_domain_enabled',
  'custom_payment_enabled',
] as const;

type VisibleEntitlementField = (typeof ENTITLEMENT_FIELDS)[number];
type EntitlementField = VisibleEntitlementField | 'custom_wechat_enabled';

type DraftIntegrationConfig = {
  public_config: Record<string, string>;
  secret_config: Record<string, string>;
  secret_configured_fields?: string[];
};

type DraftDomainStatus = BillingCustomization['domains']['items'][number];
type DomainBindResult = {
  action: string;
  binding: BillingDomainBinding;
};

const EMPTY_VALUES: Record<EntitlementField, boolean> = {
  branding_enabled: false,
  custom_domain_enabled: false,
  custom_wechat_enabled: false,
  custom_payment_enabled: false,
};

const DRAFT_PROVIDER_FIELDS: Record<
  BillingCustomizationProvider,
  { public: string[]; secret: string[] }
> = {
  wechat_oauth: { public: ['app_id'], secret: ['app_secret'] },
  pingxx: {
    public: ['app_id'],
    secret: ['secret_key', 'private_key', 'webhook_public_key'],
  },
  stripe: {
    public: ['publishable_key', 'api_version', 'currency'],
    secret: ['secret_key', 'webhook_secret'],
  },
  alipay: {
    public: ['app_id'],
    secret: ['app_private_key', 'alipay_public_key'],
  },
  wechatpay: {
    public: ['app_id', 'mch_id', 'merchant_serial_no'],
    secret: ['api_v3_key', 'private_key', 'platform_cert'],
  },
};

const VISIBLE_DRAFT_PAYMENT_PROVIDERS: BillingCustomizationProvider[] = [
  'wechatpay',
];

const INLINE_SEPARATOR = '·';

const COLLAPSED_FIELDS_STORAGE_KEY =
  'admin-billing-entitlement-dialog-collapsed-fields';

function readCollapsedFieldsPreference(): Partial<
  Record<VisibleEntitlementField, boolean>
> {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(COLLAPSED_FIELDS_STORAGE_KEY) || '{}',
    ) as Partial<Record<VisibleEntitlementField, boolean>>;
    return ENTITLEMENT_FIELDS.reduce<
      Partial<Record<VisibleEntitlementField, boolean>>
    >((result, field) => {
      if (typeof parsed[field] === 'boolean') {
        result[field] = parsed[field];
      }
      return result;
    }, {});
  } catch {
    return {};
  }
}

function writeCollapsedFieldsPreference(
  value: Partial<Record<VisibleEntitlementField, boolean>>,
) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(
    COLLAPSED_FIELDS_STORAGE_KEY,
    JSON.stringify(value),
  );
}

function createEmptyDraftIntegrationConfig(): DraftIntegrationConfig {
  return {
    public_config: {},
    secret_config: {},
    secret_configured_fields: [],
  };
}

function createEmptyDraftIntegrations(): Record<
  BillingCustomizationProvider,
  DraftIntegrationConfig
> {
  return {
    wechat_oauth: createEmptyDraftIntegrationConfig(),
    pingxx: createEmptyDraftIntegrationConfig(),
    stripe: createEmptyDraftIntegrationConfig(),
    alipay: createEmptyDraftIntegrationConfig(),
    wechatpay: createEmptyDraftIntegrationConfig(),
  };
}

function hasDraftIntegrationValue(config: DraftIntegrationConfig): boolean {
  return (
    [
      ...Object.values(config.public_config),
      ...Object.values(config.secret_config),
    ].some(value => String(value || '').trim() !== '') ||
    Boolean(config.secret_configured_fields?.length)
  );
}

function cloneDraftIntegrations(
  source: Record<BillingCustomizationProvider, DraftIntegrationConfig>,
): Record<BillingCustomizationProvider, DraftIntegrationConfig> {
  return {
    wechat_oauth: {
      public_config: { ...source.wechat_oauth.public_config },
      secret_config: { ...source.wechat_oauth.secret_config },
      secret_configured_fields: [
        ...(source.wechat_oauth.secret_configured_fields || []),
      ],
    },
    pingxx: {
      public_config: { ...source.pingxx.public_config },
      secret_config: { ...source.pingxx.secret_config },
      secret_configured_fields: [
        ...(source.pingxx.secret_configured_fields || []),
      ],
    },
    stripe: {
      public_config: { ...source.stripe.public_config },
      secret_config: { ...source.stripe.secret_config },
      secret_configured_fields: [
        ...(source.stripe.secret_configured_fields || []),
      ],
    },
    alipay: {
      public_config: { ...source.alipay.public_config },
      secret_config: { ...source.alipay.secret_config },
      secret_configured_fields: [
        ...(source.alipay.secret_configured_fields || []),
      ],
    },
    wechatpay: {
      public_config: { ...source.wechatpay.public_config },
      secret_config: { ...source.wechatpay.secret_config },
      secret_configured_fields: [
        ...(source.wechatpay.secret_configured_fields || []),
      ],
    },
  };
}

function draftIntegrationsFromCustomization(
  data: BillingCustomization,
): Record<BillingCustomizationProvider, DraftIntegrationConfig> {
  const next = createEmptyDraftIntegrations();
  for (const integration of data.integrations) {
    next[integration.provider] = {
      public_config: Object.fromEntries(
        Object.entries(integration.public_config || {}).map(([key, value]) => [
          key,
          String(value ?? ''),
        ]),
      ),
      secret_config: {},
      secret_configured_fields: [
        ...(integration.secret_configured_fields || []),
      ],
    };
  }
  return next;
}

function resolveDraftDomainStatus(
  data: BillingCustomization | null,
): DraftDomainStatus | null {
  return data?.domains.items[0] || null;
}

function resolveSelectedDraftPaymentProviders(
  draftIntegrations: Record<
    BillingCustomizationProvider,
    DraftIntegrationConfig
  >,
): BillingCustomizationProvider[] {
  return VISIBLE_DRAFT_PAYMENT_PROVIDERS.filter(provider =>
    hasDraftIntegrationValue(draftIntegrations[provider]),
  );
}

function isAdminBillingEntitlementsCacheKey(key: unknown): boolean {
  if (Array.isArray(key)) {
    return (
      typeof key[0] === 'string' &&
      key[0].startsWith('admin-billing-entitlements')
    );
  }
  return (
    typeof key === 'string' && key.startsWith('admin-billing-entitlements')
  );
}

function isAdminBillingCustomizationCacheKey(key: unknown): boolean {
  if (Array.isArray(key)) {
    return (
      typeof key[0] === 'string' &&
      key[0].startsWith('admin-billing-customization')
    );
  }
  return (
    typeof key === 'string' && key.startsWith('admin-billing-customization')
  );
}

export function AdminBillingEntitlementDialog({
  open,
  initialItem,
  initialConfigRecord,
  onOpenChange,
}: AdminBillingEntitlementDialogProps) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const isCreateFlow = !initialItem;
  const [resolvedItem, setResolvedItem] =
    React.useState<AdminBillingEntitlementItem | null>(initialItem || null);
  const [creatorMobile, setCreatorMobile] = React.useState('');
  const [values, setValues] =
    React.useState<Record<EntitlementField, boolean>>(EMPTY_VALUES);
  const [collapsedFields, setCollapsedFields] = React.useState<
    Partial<Record<VisibleEntitlementField, boolean>>
  >({});
  const [configStatus, setConfigStatus] =
    React.useState<AdminBillingConfigStatus>('pending');
  const [note, setNote] = React.useState('');
  const [draftWideLogo, setDraftWideLogo] = React.useState('');
  const [draftSquareLogo, setDraftSquareLogo] = React.useState('');
  const [draftWideLogoFile, setDraftWideLogoFile] = React.useState<File | null>(
    null,
  );
  const [draftSquareLogoFile, setDraftSquareLogoFile] =
    React.useState<File | null>(null);
  const [draftWideLogoPreview, setDraftWideLogoPreview] = React.useState('');
  const [draftSquareLogoPreview, setDraftSquareLogoPreview] =
    React.useState('');
  const [draftDomain, setDraftDomain] = React.useState('');
  const [draftDomainStatus, setDraftDomainStatus] =
    React.useState<DraftDomainStatus | null>(null);
  const [draftIntegrations, setDraftIntegrations] = React.useState<
    Record<BillingCustomizationProvider, DraftIntegrationConfig>
  >(createEmptyDraftIntegrations());
  const [selectedDraftPaymentProviders, setSelectedDraftPaymentProviders] =
    React.useState<BillingCustomizationProvider[]>([]);
  const [submitting, setSubmitting] = React.useState(false);
  const [verifyingDomain, setVerifyingDomain] = React.useState(false);
  const draftHydratedRef = React.useRef(false);
  const lastDraftTargetRef = React.useRef('');
  const draftLoadTokenRef = React.useRef(0);
  const isApplyingDraftRef = React.useRef(false);

  React.useEffect(() => {
    if (!open) return;
    setResolvedItem(initialItem || null);
    setCreatorMobile(resolveAdminBillingCreatorPrimary(initialItem || {}));
    setValues(
      initialItem
        ? {
            branding_enabled: initialItem.branding_enabled,
            custom_domain_enabled: initialItem.custom_domain_enabled,
            custom_wechat_enabled: initialItem.custom_wechat_enabled,
            custom_payment_enabled: initialItem.custom_payment_enabled,
          }
        : EMPTY_VALUES,
    );
    setCollapsedFields(readCollapsedFieldsPreference());
    setConfigStatus(initialConfigRecord?.status || 'pending');
    setNote(initialConfigRecord?.note || '');
    setDraftWideLogo('');
    setDraftSquareLogo('');
    setDraftWideLogoFile(null);
    setDraftSquareLogoFile(null);
    setDraftWideLogoPreview('');
    setDraftSquareLogoPreview('');
    setDraftDomain('');
    setDraftDomainStatus(null);
    setDraftIntegrations(createEmptyDraftIntegrations());
    setSelectedDraftPaymentProviders([]);
    setVerifyingDomain(false);
    draftHydratedRef.current = false;
    lastDraftTargetRef.current = '';
    draftLoadTokenRef.current += 1;
  }, [initialConfigRecord, initialItem, open]);

  React.useEffect(() => {
    if (
      !open ||
      submitting ||
      isApplyingDraftRef.current ||
      !draftHydratedRef.current
    ) {
      return;
    }
    const creatorBid = String(resolvedItem?.creator_bid || '').trim();
    const normalizedCreatorMobile = creatorMobile.trim();
    const canPersistByMobile =
      !creatorBid && /^\d{11}$/.test(normalizedCreatorMobile);
    if (!creatorBid && !canPersistByMobile) {
      return;
    }

    const timer = window.setTimeout(() => {
      void api.saveAdminBillingCustomizationDraft({
        creator_bid: creatorBid || undefined,
        creator_mobile: normalizedCreatorMobile || undefined,
        branding_enabled: values.branding_enabled,
        custom_domain_enabled: values.custom_domain_enabled,
        custom_wechat_enabled: values.custom_wechat_enabled,
        custom_payment_enabled: values.custom_payment_enabled,
        config_status: configStatus,
        note,
        branding: {
          logo_wide_url: draftWideLogo,
          logo_square_url: draftSquareLogo,
        },
        domain: {
          host: draftDomain,
        },
        integrations: cloneDraftIntegrations(draftIntegrations),
      });
    }, 500);

    return () => window.clearTimeout(timer);
  }, [
    configStatus,
    creatorMobile,
    draftDomain,
    draftDomainStatus,
    draftIntegrations,
    draftSquareLogo,
    draftSquareLogoFile,
    draftSquareLogoPreview,
    draftWideLogo,
    draftWideLogoFile,
    draftWideLogoPreview,
    note,
    open,
    resolvedItem?.creator_bid,
    submitting,
    values,
  ]);

  React.useEffect(() => {
    if (!open || submitting) {
      return;
    }
    const creatorBid = String(resolvedItem?.creator_bid || '').trim();
    const normalizedCreatorMobile = creatorMobile.trim();
    const targetKey = creatorBid
      ? `creator:${creatorBid}`
      : /^\d{11}$/.test(normalizedCreatorMobile)
        ? `mobile:${normalizedCreatorMobile}`
        : '';
    if (!targetKey || lastDraftTargetRef.current === targetKey) {
      return;
    }

    lastDraftTargetRef.current = targetKey;
    draftHydratedRef.current = false;
    const loadToken = draftLoadTokenRef.current + 1;
    draftLoadTokenRef.current = loadToken;
    void (async () => {
      try {
        const draft = (await api.getAdminBillingCustomizationDraft(
          creatorBid
            ? { creator_bid: creatorBid }
            : { creator_mobile: normalizedCreatorMobile },
          { skipErrorToast: true },
        )) as AdminBillingCustomizationDraft;
        if (
          draftLoadTokenRef.current !== loadToken ||
          lastDraftTargetRef.current !== targetKey
        ) {
          return;
        }
        const hasSavedDraftContent =
          draft.branding_enabled ||
          draft.custom_domain_enabled ||
          draft.custom_wechat_enabled ||
          draft.custom_payment_enabled ||
          draft.config_status !== 'pending' ||
          Boolean(draft.note?.trim()) ||
          Boolean(draft.branding?.logo_wide_url) ||
          Boolean(draft.branding?.logo_square_url) ||
          Boolean(draft.domain?.host) ||
          Object.values(draft.integrations || {}).some(
            integration =>
              [
                ...Object.values(integration?.public_config || {}),
                ...Object.values(integration?.secret_config || {}),
              ].some(value => String(value || '').trim() !== '') ||
              Boolean(integration?.secret_configured_fields?.length),
          );
        if (!hasSavedDraftContent) {
          if (creatorBid) {
            const customization = (await api.getAdminBillingCustomization(
              { creator_bid: creatorBid },
              { skipErrorToast: true },
            )) as BillingCustomization;
            if (
              draftLoadTokenRef.current !== loadToken ||
              lastDraftTargetRef.current !== targetKey
            ) {
              return;
            }
            const nextDraftIntegrations =
              draftIntegrationsFromCustomization(customization);
            const nextDraftDomainStatus =
              resolveDraftDomainStatus(customization);
            isApplyingDraftRef.current = true;
            setDraftWideLogo(customization.branding.logo_wide_url || '');
            setDraftSquareLogo(customization.branding.logo_square_url || '');
            setDraftWideLogoPreview(customization.branding.logo_wide_url || '');
            setDraftSquareLogoPreview(
              customization.branding.logo_square_url || '',
            );
            setDraftDomain(customization.domains.items[0]?.host || '');
            setDraftDomainStatus(nextDraftDomainStatus);
            setDraftIntegrations(nextDraftIntegrations);
            setSelectedDraftPaymentProviders(
              resolveSelectedDraftPaymentProviders(nextDraftIntegrations),
            );
          }
          draftHydratedRef.current = true;
          return;
        }
        isApplyingDraftRef.current = true;
        setValues({
          branding_enabled: draft.branding_enabled,
          custom_domain_enabled: draft.custom_domain_enabled,
          custom_wechat_enabled: draft.custom_wechat_enabled,
          custom_payment_enabled: draft.custom_payment_enabled,
        });
        setConfigStatus(draft.config_status);
        setNote(draft.note || '');
        setDraftWideLogo(draft.branding.logo_wide_url || '');
        setDraftSquareLogo(draft.branding.logo_square_url || '');
        setDraftWideLogoPreview(draft.branding.logo_wide_url || '');
        setDraftSquareLogoPreview(draft.branding.logo_square_url || '');
        setDraftDomain(draft.domain.host || '');
        if (creatorBid) {
          const customization = (await api.getAdminBillingCustomization(
            { creator_bid: creatorBid },
            { skipErrorToast: true },
          )) as BillingCustomization;
          if (
            draftLoadTokenRef.current !== loadToken ||
            lastDraftTargetRef.current !== targetKey
          ) {
            return;
          }
          setDraftDomainStatus(resolveDraftDomainStatus(customization));
        }
        const nextDraftIntegrations = cloneDraftIntegrations(
          draft.integrations || createEmptyDraftIntegrations(),
        );
        setDraftIntegrations(nextDraftIntegrations);
        setSelectedDraftPaymentProviders(
          resolveSelectedDraftPaymentProviders(nextDraftIntegrations),
        );
        draftHydratedRef.current = true;
      } catch {
        if (draftLoadTokenRef.current === loadToken) {
          lastDraftTargetRef.current = '';
          draftHydratedRef.current = true;
        }
      } finally {
        window.setTimeout(() => {
          if (draftLoadTokenRef.current === loadToken) {
            isApplyingDraftRef.current = false;
          }
        }, 0);
      }
    })();
  }, [creatorMobile, open, resolvedItem?.creator_bid, submitting]);

  const handleDraftLogoSelection = React.useCallback(
    async (target: 'wide' | 'square', file: File | null) => {
      if (!file) {
        if (target === 'wide') {
          setDraftWideLogoFile(null);
          setDraftWideLogoPreview('');
        } else {
          setDraftSquareLogoFile(null);
          setDraftSquareLogoPreview('');
        }
        return;
      }

      const creatorBid = String(resolvedItem?.creator_bid || '').trim();
      const normalizedCreatorMobile = creatorMobile.trim();
      const canUploadDraft = Boolean(
        creatorBid || /^\d{11}$/.test(normalizedCreatorMobile),
      );
      if (!canUploadDraft) {
        const localPreview = URL.createObjectURL(file);
        if (target === 'wide') {
          setDraftWideLogoFile(file);
          setDraftWideLogoPreview(localPreview);
        } else {
          setDraftSquareLogoFile(file);
          setDraftSquareLogoPreview(localPreview);
        }
        return;
      }

      const { uploadFile } = await import('@/lib/file');
      const response = await uploadFile(
        file,
        '/api/admin/billing/customization-draft/branding/logo',
        {
          target,
          creator_bid: creatorBid,
          creator_mobile: normalizedCreatorMobile,
        },
      );
      const payload = await response.json();
      if (!response.ok || payload.code !== 0) {
        throw new Error(
          payload.message ||
            t('module.billing.customization.branding.uploadFailed'),
        );
      }
      const uploadedUrl = String(payload.data || '');
      if (target === 'wide') {
        setDraftWideLogo(uploadedUrl);
        setDraftWideLogoFile(null);
        setDraftWideLogoPreview(uploadedUrl);
      } else {
        setDraftSquareLogo(uploadedUrl);
        setDraftSquareLogoFile(null);
        setDraftSquareLogoPreview(uploadedUrl);
      }
    },
    [creatorMobile, resolvedItem?.creator_bid, t],
  );

  const handleSubmit = async () => {
    const normalizedCreatorMobile = creatorMobile.trim();
    if (!resolvedItem && !normalizedCreatorMobile) {
      toast({
        title: t(
          'module.billing.admin.entitlements.grant.errors.creatorMobileRequired',
        ),
        variant: 'destructive',
      });
      return;
    }

    setSubmitting(true);
    try {
      const effectiveValues = { ...values };

      const payload: AdminBillingEntitlementGrantPayload = {
        ...(resolvedItem?.creator_bid
          ? { creator_bid: resolvedItem.creator_bid }
          : { creator_mobile: normalizedCreatorMobile }),
        ...effectiveValues,
      };
      const response = await api.grantAdminBillingEntitlement(payload);
      const nextCreatorBid = String(
        (response as { creator_bid?: string } | undefined)?.creator_bid ||
          resolvedItem?.creator_bid ||
          '',
      ).trim();

      if (nextCreatorBid) {
        let nextWideLogo = draftWideLogo;
        let nextSquareLogo = draftSquareLogo;

        if (
          values.branding_enabled &&
          (draftWideLogoFile || draftSquareLogoFile)
        ) {
          const { uploadFile } = await import('@/lib/file');
          if (draftWideLogoFile) {
            const response = await uploadFile(
              draftWideLogoFile,
              `/api/admin/billing/customization/${nextCreatorBid}/branding/logo`,
              { target: 'wide' },
            );
            const payload = await response.json();
            if (!response.ok || payload.code !== 0) {
              throw new Error(
                payload.message ||
                  t('module.billing.customization.branding.uploadFailed'),
              );
            }
            nextWideLogo = String(payload.data || '');
          }
          if (draftSquareLogoFile) {
            const response = await uploadFile(
              draftSquareLogoFile,
              `/api/admin/billing/customization/${nextCreatorBid}/branding/logo`,
              { target: 'square' },
            );
            const payload = await response.json();
            if (!response.ok || payload.code !== 0) {
              throw new Error(
                payload.message ||
                  t('module.billing.customization.branding.uploadFailed'),
              );
            }
            nextSquareLogo = String(payload.data || '');
          }
        }

        if (values.branding_enabled && (nextWideLogo || nextSquareLogo)) {
          await api.updateAdminBillingCustomizationBranding({
            creator_bid: nextCreatorBid,
            logo_wide_url: nextWideLogo,
            logo_square_url: nextSquareLogo,
          });
        }

        const normalizedDraftDomain = draftDomain.trim();
        const existingDomain = draftDomainStatus?.host || '';
        if (
          values.custom_domain_enabled &&
          normalizedDraftDomain &&
          normalizedDraftDomain !== existingDomain
        ) {
          await api.createAdminBillingCustomizationDomain({
            creator_bid: nextCreatorBid,
            host: normalizedDraftDomain,
          });
        }

        const providersToApply = values.custom_payment_enabled
          ? selectedDraftPaymentProviders.filter(provider =>
              hasDraftIntegrationValue(draftIntegrations[provider]),
            )
          : [];

        for (const provider of providersToApply) {
          const integrationDraft = draftIntegrations[provider];
          if (!hasDraftIntegrationValue(integrationDraft)) {
            continue;
          }

          await api.saveAdminBillingCustomizationIntegration({
            creator_bid: nextCreatorBid,
            provider,
            public_config: integrationDraft.public_config,
            secret_config: integrationDraft.secret_config,
          });
        }
      }

      if (nextCreatorBid) {
        setResolvedItem(current => ({
          creator_bid: nextCreatorBid,
          creator_mobile:
            normalizedCreatorMobile || current?.creator_mobile || '',
          creator_nickname: current?.creator_nickname || '',
          creator_identify: current?.creator_identify || '',
          source_kind: current?.source_kind || 'default',
          source_type: current?.source_type || '',
          source_bid: current?.source_bid || '',
          product_bid: current?.product_bid || '',
          product_name_key: current?.product_name_key || '',
          effective_from: current?.effective_from || null,
          effective_to: current?.effective_to || null,
          feature_payload: current?.feature_payload || {},
          branding_enabled: effectiveValues.branding_enabled,
          custom_domain_enabled: effectiveValues.custom_domain_enabled,
          custom_wechat_enabled: effectiveValues.custom_wechat_enabled,
          custom_payment_enabled: effectiveValues.custom_payment_enabled,
          priority_class: current?.priority_class || 'standard',
          analytics_tier: current?.analytics_tier || 'basic',
          support_tier: current?.support_tier || 'self_serve',
        }));
      }

      if (nextCreatorBid) {
        await setAdminBillingConfigStatusState(nextCreatorBid, {
          status: configStatus,
          note: note.trim(),
        });
      }
      await api.deleteAdminBillingCustomizationDraft(
        nextCreatorBid
          ? { creator_bid: nextCreatorBid }
          : { creator_mobile: normalizedCreatorMobile },
      );
      await mutate(isAdminBillingEntitlementsCacheKey);
      await mutate(isAdminBillingCustomizationCacheKey);
      if (!resolvedItem && nextCreatorBid) {
        toast({
          title: t('module.billing.admin.entitlements.grant.createdContinue', {
            creator: normalizedCreatorMobile,
          }),
        });
        return;
      }

      onOpenChange(false);
      toast({
        title: t('module.billing.admin.entitlements.grant.success', {
          creator:
            normalizedCreatorMobile ||
            resolveAdminBillingCreatorPrimary(resolvedItem || {}),
        }),
      });
    } catch {
      // The shared request layer already surfaces backend errors.
    } finally {
      setSubmitting(false);
    }
  };

  const renderInlineConfig = (field: VisibleEntitlementField) => {
    if (!values[field] || collapsedFields[field]) {
      return null;
    }

    return (
      <div className='border-t border-slate-200 bg-slate-50/70 px-4 py-4'>
        <CreateDraftSection
          field={field}
          draftDomain={draftDomain}
          draftDomainStatus={draftDomainStatus}
          creatorBid={resolvedItem?.creator_bid || ''}
          draftIntegrations={draftIntegrations}
          verifyingDomain={verifyingDomain}
          draftSquareLogoFile={draftSquareLogoFile}
          draftSquareLogoPreview={draftSquareLogoPreview}
          draftSquareLogo={draftSquareLogo}
          draftWideLogoFile={draftWideLogoFile}
          draftWideLogoPreview={draftWideLogoPreview}
          draftWideLogo={draftWideLogo}
          selectedPaymentProviders={selectedDraftPaymentProviders}
          onSelectedPaymentProvidersChange={setSelectedDraftPaymentProviders}
          onDraftDomainChange={setDraftDomain}
          onDraftDomainStatusChange={setDraftDomainStatus}
          onVerifyDraftDomain={async domain => {
            if (!resolvedItem?.creator_bid || !domain.domain_binding_bid) {
              return;
            }
            setVerifyingDomain(true);
            try {
              const result = (await api.verifyAdminBillingCustomizationDomain({
                creator_bid: resolvedItem.creator_bid,
                domain_binding_bid: domain.domain_binding_bid,
              })) as DomainBindResult;
              const nextBinding = result.binding || domain;
              setDraftDomainStatus(nextBinding);
              toast({
                title: t(
                  nextBinding.status === 'verified'
                    ? 'module.billing.customization.domain.verifySuccess'
                    : 'module.billing.customization.domain.verifyFailed',
                ),
              });
              await mutate(isAdminBillingCustomizationCacheKey);
            } finally {
              setVerifyingDomain(false);
            }
          }}
          onDraftIntegrationChange={(provider, section, key, value) => {
            setDraftIntegrations(current => ({
              ...current,
              [provider]: {
                ...current[provider],
                [section]: {
                  ...current[provider][section],
                  [key]: value,
                },
              },
            }));
          }}
          onDraftSquareLogoFileChange={file => {
            void handleDraftLogoSelection('square', file).catch(error => {
              toast({
                title:
                  error instanceof Error
                    ? error.message
                    : t('module.billing.customization.branding.uploadFailed'),
                variant: 'destructive',
              });
            });
          }}
          onDraftSquareLogoChange={setDraftSquareLogo}
          onDraftWideLogoFileChange={file => {
            void handleDraftLogoSelection('wide', file).catch(error => {
              toast({
                title:
                  error instanceof Error
                    ? error.message
                    : t('module.billing.customization.branding.uploadFailed'),
                variant: 'destructive',
              });
            });
          }}
          onDraftWideLogoChange={setDraftWideLogo}
        />
      </div>
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!submitting) onOpenChange(nextOpen);
      }}
    >
      <DialogContent className='flex max-h-[88vh] w-[calc(100vw-32px)] flex-col gap-0 overflow-hidden border-slate-200 bg-white p-0 shadow-xl sm:max-w-[760px]'>
        <DialogHeader className='shrink-0 border-b border-slate-200 px-6 pb-5 pt-6'>
          <DialogTitle>
            {t(
              isCreateFlow
                ? 'module.billing.admin.entitlements.grant.title'
                : resolvedItem
                  ? 'module.billing.admin.entitlements.grant.editTitle'
                  : 'module.billing.admin.entitlements.grant.title',
            )}
          </DialogTitle>
          <DialogDescription>
            {t('module.billing.admin.entitlements.grant.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='min-h-0 flex-1 overflow-y-auto px-6 py-5'>
          <div className='space-y-5'>
            <div className='grid gap-2'>
              <div className='grid gap-2'>
                <label
                  htmlFor='admin-billing-entitlement-creator-mobile'
                  className='text-sm font-medium text-slate-900'
                >
                  {t(
                    'module.billing.admin.entitlements.grant.fields.creatorMobile',
                  )}
                </label>
                <Input
                  id='admin-billing-entitlement-creator-mobile'
                  value={creatorMobile}
                  disabled={Boolean(resolvedItem) || submitting}
                  placeholder={t(
                    'module.billing.admin.entitlements.grant.creatorMobilePlaceholder',
                  )}
                  onChange={event => setCreatorMobile(event.target.value)}
                />
              </div>
            </div>

            <div className='space-y-3'>
              {ENTITLEMENT_FIELDS.map(field => (
                <div
                  key={field}
                  className='overflow-hidden rounded-xl border border-slate-200 bg-white'
                >
                  <div
                    role='button'
                    tabIndex={submitting ? -1 : 0}
                    data-clickable='true'
                    aria-disabled={submitting}
                    className='flex cursor-pointer items-start justify-between gap-4 px-4 py-4 transition-colors hover:bg-slate-50'
                    onClick={() => {
                      if (submitting) {
                        return;
                      }
                      setValues(current => {
                        const nextValue = !current[field];
                        if (nextValue) {
                          setCollapsedFields(fields => ({
                            ...fields,
                            [field]: false,
                          }));
                        }
                        return { ...current, [field]: nextValue };
                      });
                    }}
                    onKeyDown={event => {
                      if (submitting) {
                        return;
                      }
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setValues(current => {
                          const nextValue = !current[field];
                          if (nextValue) {
                            setCollapsedFields(fields => ({
                              ...fields,
                              [field]: false,
                            }));
                          }
                          return {
                            ...current,
                            [field]: nextValue,
                          };
                        });
                      }
                    }}
                  >
                    <div className='min-w-0 space-y-2'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <label
                          htmlFor={`admin-billing-entitlement-${field}`}
                          className='cursor-pointer text-sm font-medium text-slate-900'
                        >
                          {t(
                            `module.billing.admin.entitlements.grant.fields.${field}`,
                          )}
                        </label>
                        <span
                          className={
                            values[field]
                              ? 'rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700'
                              : 'rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500'
                          }
                        >
                          {values[field]
                            ? t(
                                'module.billing.admin.entitlements.grant.enabled',
                              )
                            : t(
                                'module.billing.admin.entitlements.grant.disabled',
                              )}
                        </span>
                      </div>
                      <p className='text-xs leading-5 text-slate-500'>
                        {t(
                          `module.billing.admin.entitlements.grant.pendingConfiguration.${field}`,
                        )}
                      </p>
                    </div>
                    <div className='flex shrink-0 items-center gap-2'>
                      {values[field] ? (
                        <button
                          type='button'
                          data-clickable='true'
                          className='inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900'
                          aria-label={t(
                            collapsedFields[field]
                              ? 'common.expand'
                              : 'common.collapse',
                          )}
                          aria-expanded={!collapsedFields[field]}
                          onClick={event => {
                            event.stopPropagation();
                            setCollapsedFields(current => {
                              const next = {
                                ...current,
                                [field]: !current[field],
                              };
                              writeCollapsedFieldsPreference(next);
                              return next;
                            });
                          }}
                        >
                          <ChevronDown
                            className={`h-4 w-4 transition-transform ${
                              collapsedFields[field] ? '-rotate-90' : ''
                            }`}
                          />
                        </button>
                      ) : null}
                      <Switch
                        id={`admin-billing-entitlement-${field}`}
                        checked={values[field]}
                        disabled={submitting}
                        className='mt-0.5 data-[state=unchecked]:bg-slate-300'
                        onClick={event => {
                          event.stopPropagation();
                        }}
                        onCheckedChange={checked => {
                          if (checked) {
                            setCollapsedFields(current => ({
                              ...current,
                              [field]: false,
                            }));
                          }
                          setValues(current => ({
                            ...current,
                            [field]: checked,
                          }));
                        }}
                      />
                    </div>
                  </div>

                  {renderInlineConfig(field)}
                </div>
              ))}
            </div>

            <div className='rounded-xl border border-slate-200 bg-white p-4'>
              <label
                htmlFor='admin-billing-entitlement-note'
                className='text-sm font-medium text-slate-900'
              >
                {t('module.billing.admin.entitlements.grant.fields.note')}
              </label>
              <Textarea
                id='admin-billing-entitlement-note'
                className='mt-3'
                value={note}
                disabled={submitting}
                placeholder={t(
                  'module.billing.admin.entitlements.grant.notePlaceholder',
                )}
                onChange={event => setNote(event.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter className='shrink-0 border-t border-slate-200 px-6 py-4'>
          <Button
            type='button'
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('module.billing.admin.entitlements.grant.cancel')}
          </Button>
          <Button
            type='button'
            disabled={submitting}
            onClick={handleSubmit}
          >
            {submitting
              ? t('module.billing.admin.entitlements.grant.submitting')
              : t('module.billing.admin.entitlements.grant.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CreateDraftSection({
  field,
  creatorBid,
  draftDomain,
  draftDomainStatus,
  draftIntegrations,
  verifyingDomain,
  draftSquareLogoFile,
  draftSquareLogoPreview,
  draftSquareLogo,
  draftWideLogoFile,
  draftWideLogoPreview,
  draftWideLogo,
  selectedPaymentProviders,
  onSelectedPaymentProvidersChange,
  onDraftDomainChange,
  onDraftDomainStatusChange,
  onVerifyDraftDomain,
  onDraftIntegrationChange,
  onDraftSquareLogoFileChange,
  onDraftSquareLogoChange,
  onDraftWideLogoFileChange,
  onDraftWideLogoChange,
}: {
  field: VisibleEntitlementField;
  creatorBid: string;
  draftDomain: string;
  draftDomainStatus: DraftDomainStatus | null;
  draftIntegrations: Record<
    BillingCustomizationProvider,
    DraftIntegrationConfig
  >;
  verifyingDomain: boolean;
  draftSquareLogoFile: File | null;
  draftSquareLogoPreview: string;
  draftSquareLogo: string;
  draftWideLogoFile: File | null;
  draftWideLogoPreview: string;
  draftWideLogo: string;
  selectedPaymentProviders: BillingCustomizationProvider[];
  onSelectedPaymentProvidersChange: (
    providers: BillingCustomizationProvider[],
  ) => void;
  onDraftDomainChange: (value: string) => void;
  onDraftDomainStatusChange: (value: DraftDomainStatus | null) => void;
  onVerifyDraftDomain: (domain: DraftDomainStatus) => Promise<void>;
  onDraftIntegrationChange: (
    provider: BillingCustomizationProvider,
    section: 'public_config' | 'secret_config',
    key: string,
    value: string,
  ) => void;
  onDraftSquareLogoFileChange: (file: File | null) => void;
  onDraftSquareLogoChange: (value: string) => void;
  onDraftWideLogoFileChange: (file: File | null) => void;
  onDraftWideLogoChange: (value: string) => void;
}) {
  const { t } = useTranslation();

  if (field === 'branding_enabled') {
    return (
      <div className='grid gap-4 md:grid-cols-2'>
        <CreateDraftLogoField
          label={t('module.billing.customization.branding.wideLogo')}
          hint={t('module.billing.customization.branding.wideHint')}
          uploadLabel={t('module.billing.customization.branding.uploadWide')}
          previewUrl={draftWideLogoPreview}
          shape='wide'
          file={draftWideLogoFile}
          value={draftWideLogo}
          onChange={onDraftWideLogoChange}
          onFileChange={onDraftWideLogoFileChange}
        />
        <CreateDraftLogoField
          label={t('module.billing.customization.branding.squareLogo')}
          hint={t('module.billing.customization.branding.squareHint')}
          uploadLabel={t('module.billing.customization.branding.uploadSquare')}
          previewUrl={draftSquareLogoPreview}
          shape='square'
          file={draftSquareLogoFile}
          value={draftSquareLogo}
          onChange={onDraftSquareLogoChange}
          onFileChange={onDraftSquareLogoFileChange}
        />
      </div>
    );
  }

  if (field === 'custom_domain_enabled') {
    return (
      <div className='space-y-3'>
        <CreateDraftInput
          label={t('module.billing.customization.domain.title')}
          value={draftDomain}
          onChange={value => {
            onDraftDomainChange(value);
            if (draftDomainStatus && value.trim() !== draftDomainStatus.host) {
              onDraftDomainStatusChange(null);
            }
          }}
          placeholder={t('module.billing.customization.domain.placeholder')}
        />
        {draftDomainStatus ? (
          <div className='rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm'>
            <div className='font-medium text-slate-900'>
              {draftDomainStatus.host}
            </div>
            <div className='mt-1 text-xs text-slate-500'>
              {t(`module.billing.domains.status.${draftDomainStatus.status}`)}{' '}
              {INLINE_SEPARATOR}{' '}
              {t(`module.billing.domains.ssl.${draftDomainStatus.ssl_status}`)}
            </div>
            {draftDomainStatus.verification_record_name &&
            draftDomainStatus.verification_record_value ? (
              <div className='mt-2 break-all rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500'>
                {t('module.billing.customization.domain.record', {
                  name: draftDomainStatus.verification_record_name,
                  value: draftDomainStatus.verification_record_value,
                })}
              </div>
            ) : null}
            {creatorBid ? (
              <div className='mt-3'>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={verifyingDomain}
                  onClick={() => {
                    void onVerifyDraftDomain(draftDomainStatus);
                  }}
                >
                  {t('module.billing.customization.domain.verify')}
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className='space-y-4'>
      <PaymentProviderSelector
        selectedProviders={selectedPaymentProviders}
        onSelectedProvidersChange={onSelectedPaymentProvidersChange}
      />
      {selectedPaymentProviders.map(provider => (
        <CreateDraftIntegrationFields
          key={provider}
          provider={provider}
          config={draftIntegrations[provider]}
          onChange={onDraftIntegrationChange}
        />
      ))}
    </div>
  );
}

function PaymentProviderSelector({
  selectedProviders,
  onSelectedProvidersChange,
}: {
  selectedProviders: BillingCustomizationProvider[];
  onSelectedProvidersChange: (
    providers: BillingCustomizationProvider[],
  ) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className='space-y-3'>
      <div className='space-y-1'>
        <div className='text-sm font-medium text-slate-900'>
          {t('module.billing.customization.paymentProvider.title')}
        </div>
        <p className='text-xs leading-5 text-slate-500'>
          {t('module.billing.customization.paymentProvider.description')}
        </p>
      </div>
      <div className='grid gap-2 sm:grid-cols-2'>
        {VISIBLE_DRAFT_PAYMENT_PROVIDERS.map(provider => {
          const selected = selectedProviders.includes(provider);
          return (
            <button
              key={provider}
              type='button'
              role='checkbox'
              data-clickable='true'
              className={`flex items-center gap-3 rounded-xl border px-3 py-3 text-left text-sm transition-colors ${
                selected
                  ? 'border-blue-300 bg-blue-50 text-slate-950 shadow-[0_0_0_1px_rgba(59,130,246,0.18)]'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
              }`}
              aria-checked={selected}
              onClick={() => {
                onSelectedProvidersChange(
                  selected
                    ? selectedProviders.filter(item => item !== provider)
                    : [...selectedProviders, provider],
                );
              }}
            >
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                  selected ? 'border-blue-600 bg-blue-600' : 'border-slate-300'
                }`}
              >
                {selected ? (
                  <span className='h-2 w-2 rounded-sm bg-white' />
                ) : null}
              </span>
              <span className='font-medium'>
                {t(`module.billing.customization.providers.${provider}`)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CreateDraftLogoField({
  file,
  hint,
  label,
  onChange,
  onFileChange,
  previewUrl,
  shape = 'wide',
  uploadLabel,
  value,
}: {
  file: File | null;
  hint: string;
  label: string;
  onChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  previewUrl: string;
  shape?: 'wide' | 'square';
  uploadLabel: string;
  value: string;
}) {
  const { t } = useTranslation();
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  return (
    <div className='flex h-full flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm'>
      <div className='min-h-[88px] space-y-1'>
        <div className='text-sm font-medium text-slate-900'>{label}</div>
        <div className='text-xs leading-5 text-slate-500'>{hint}</div>
      </div>
      <div
        className={`flex items-center justify-center overflow-hidden rounded-xl border border-dashed border-slate-300 bg-slate-50 ${
          shape === 'square' ? 'min-h-[116px] w-[116px]' : 'min-h-[116px]'
        }`}
      >
        {previewUrl || value ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl || value}
            alt={label}
            className={
              shape === 'square'
                ? 'h-[116px] w-[116px] object-contain'
                : 'max-h-[116px] max-w-full object-contain'
            }
          />
        ) : (
          <div className='flex flex-col items-center gap-2 px-4 py-6 text-center text-slate-400'>
            <ImagePlus className='h-7 w-7' />
            <span className='text-xs'>{uploadLabel}</span>
          </div>
        )}
      </div>
      <input
        ref={inputRef}
        type='file'
        accept='image/png,image/jpeg,image/webp'
        className='hidden'
        onChange={event => {
          const nextFile = event.target.files?.[0] || null;
          onFileChange(nextFile);
          event.currentTarget.value = '';
        }}
      />
      <Input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={
          file
            ? file.name
            : t('module.billing.customization.branding.urlPlaceholder')
        }
      />
      <div className='mt-auto flex flex-wrap gap-2 pt-1'>
        <Button
          type='button'
          variant='outline'
          onClick={() => inputRef.current?.click()}
        >
          {uploadLabel}
        </Button>
        {previewUrl || value ? (
          <Button
            type='button'
            variant='ghost'
            onClick={() => {
              onFileChange(null);
              onChange('');
            }}
          >
            {t('module.billing.customization.actions.clear')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function CreateDraftInput({
  hint,
  label,
  onChange,
  placeholder,
  value,
}: {
  hint?: string;
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <label className='grid gap-2 text-sm'>
      <span className='font-medium text-slate-900'>{label}</span>
      {hint ? (
        <span className='text-xs leading-5 text-slate-500'>{hint}</span>
      ) : null}
      <Input
        value={value}
        placeholder={placeholder}
        onChange={event => onChange(event.target.value)}
      />
    </label>
  );
}

function CreateDraftIntegrationFields({
  provider,
  config,
  onChange,
}: {
  provider: BillingCustomizationProvider;
  config: DraftIntegrationConfig;
  onChange: (
    provider: BillingCustomizationProvider,
    section: 'public_config' | 'secret_config',
    key: string,
    value: string,
  ) => void;
}) {
  const { t } = useTranslation();
  const fields = DRAFT_PROVIDER_FIELDS[provider];

  return (
    <div className='rounded-xl border border-slate-200 bg-white p-4 shadow-sm'>
      <div className='mb-3 text-sm font-medium text-slate-900'>
        {t(`module.billing.customization.providers.${provider}`)}
      </div>
      {fields.public.length ? (
        <div className='grid gap-3 md:grid-cols-2'>
          {fields.public.map(field => (
            <CreateDraftInput
              key={`${provider}-public-${field}`}
              label={field}
              value={config.public_config[field] || ''}
              onChange={value =>
                onChange(provider, 'public_config', field, value)
              }
            />
          ))}
        </div>
      ) : null}
      {fields.secret.length ? (
        <div className='mt-4 grid gap-3 md:grid-cols-2'>
          {fields.secret.map(field => (
            <label
              key={`${provider}-secret-${field}`}
              className='grid gap-2 text-sm'
            >
              <span className='font-medium text-slate-900'>{field}</span>
              {field.includes('key') || field.includes('cert') ? (
                <Textarea
                  rows={4}
                  value={config.secret_config[field] || ''}
                  placeholder={
                    config.secret_configured_fields?.includes(field)
                      ? t('module.billing.customization.actions.secretSaved')
                      : undefined
                  }
                  onChange={event =>
                    onChange(
                      provider,
                      'secret_config',
                      field,
                      event.target.value,
                    )
                  }
                />
              ) : (
                <Input
                  type='password'
                  value={config.secret_config[field] || ''}
                  placeholder={
                    config.secret_configured_fields?.includes(field)
                      ? t('module.billing.customization.actions.secretSaved')
                      : undefined
                  }
                  onChange={event =>
                    onChange(
                      provider,
                      'secret_config',
                      field,
                      event.target.value,
                    )
                  }
                />
              )}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
