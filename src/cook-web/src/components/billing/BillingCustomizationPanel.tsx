'use client';

import React from 'react';
import { ImagePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import useSWR, { useSWRConfig } from 'swr';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { Button } from '@/components/ui/Button';
import { buildBillingSwrKey } from '@/lib/billing';
import type {
  BillingCustomization,
  BillingCustomizationIntegration,
  BillingCustomizationProvider,
} from '@/types/billing';

const PROVIDER_FIELDS: Record<
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

const BILLING_PASSIVE_REQUEST_CONFIG = {
  skipErrorToast: true,
} as const;

const VISIBLE_PAYMENT_CUSTOMIZATION_PROVIDERS: BillingCustomizationProvider[] =
  ['alipay', 'wechatpay'];
const DNS_TXT_RECORD_TYPE = 'TXT';

function LockedNotice() {
  const { t } = useTranslation();
  return (
    <p className='rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800'>
      {t('module.billing.customization.locked')}
    </p>
  );
}

function PendingActivationNotice() {
  const { t } = useTranslation();
  return (
    <p className='rounded-lg bg-sky-50 px-4 py-3 text-sm text-sky-700'>
      {t('module.billing.customization.pendingActivation')}
    </p>
  );
}

export function BillingCustomizationPanel() {
  return <BillingCustomizationPanelContent />;
}

type BillingCustomizationPanelContentProps = {
  creatorBid?: string;
  disabled?: boolean;
  sectionFilter?: Array<
    'branding' | 'custom_domain' | 'custom_wechat' | 'custom_payment'
  >;
  capabilityOverrides?: Partial<
    Record<
      'branding' | 'custom_domain' | 'custom_wechat' | 'custom_payment',
      boolean
    >
  >;
  embedded?: boolean;
  loadingFallback?: React.ReactNode;
};

type BillingCustomizationEditorState = {
  creatorBid?: string;
  data: BillingCustomization | null;
  error: string;
  info: string;
  isAdminMode: boolean;
  isLoading: boolean;
  saving: string;
  domain: string;
  setDomain: React.Dispatch<React.SetStateAction<string>>;
  squareLogoPreview: string;
  squareLogo: string;
  setSquareLogoPreview: (value: string) => void;
  setSquareLogo: React.Dispatch<React.SetStateAction<string>>;
  setWideLogoPreview: (value: string) => void;
  wideLogoPreview: string;
  wideLogo: string;
  setWideLogo: React.Dispatch<React.SetStateAction<string>>;
  run: (key: string, action: () => Promise<unknown>) => Promise<void>;
  uploadLogo: (target: 'wide' | 'square', file?: File) => Promise<void>;
};

export function BillingCustomizationPanelContent({
  creatorBid,
  disabled = false,
  sectionFilter,
  capabilityOverrides,
  embedded = false,
  loadingFallback,
}: BillingCustomizationPanelContentProps = {}) {
  const { t } = useTranslation();
  const editor = useBillingCustomizationEditorState({ creatorBid, disabled });
  const [selectedPaymentProviders, setSelectedPaymentProviders] =
    React.useState<BillingCustomizationProvider[]>([]);

  React.useEffect(() => {
    if (!editor.data) {
      return;
    }
    const configuredProviders = editor.data.integrations
      .filter(
        integration =>
          VISIBLE_PAYMENT_CUSTOMIZATION_PROVIDERS.includes(
            integration.provider,
          ) && integration.status !== 'unconfigured',
      )
      .map(integration => integration.provider);
    setSelectedPaymentProviders(current => {
      if (configuredProviders.length > 0) {
        return configuredProviders;
      }
      const next = current.filter(provider =>
        VISIBLE_PAYMENT_CUSTOMIZATION_PROVIDERS.includes(provider),
      );
      return next;
    });
  }, [editor.data]);

  if (disabled) {
    return null;
  }

  if (editor.isLoading || !editor.data) {
    if (embedded) {
      return loadingFallback ? <>{loadingFallback}</> : null;
    }

    return (
      <div className='space-y-4 rounded-xl border border-slate-200 bg-white p-4'>
        <div className='h-5 w-32 animate-pulse rounded bg-slate-200' />
        <div className='grid gap-4 md:grid-cols-2'>
          <div className='h-40 animate-pulse rounded-xl bg-slate-100' />
          <div className='h-40 animate-pulse rounded-xl bg-slate-100' />
        </div>
        <div className='text-sm text-slate-500'>
          {t('module.billing.customization.loading')}
        </div>
      </div>
    );
  }

  const filteredSections = sectionFilter || [
    'branding',
    'custom_domain',
    'custom_payment',
  ];
  const data = editor.data;
  const canEditBranding =
    capabilityOverrides?.branding ?? data.capabilities.branding;
  const canEditDomain =
    capabilityOverrides?.custom_domain ?? data.capabilities.custom_domain;
  const canEditWechat =
    capabilityOverrides?.custom_wechat ?? data.capabilities.custom_wechat;
  const canEditPayment =
    capabilityOverrides?.custom_payment ?? data.capabilities.custom_payment;

  return (
    <div
      className={embedded ? 'space-y-4' : 'space-y-8 pb-8'}
      data-testid='billing-customization-panel'
    >
      {editor.error ? (
        <p
          role='alert'
          className='rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700'
        >
          {editor.error}
        </p>
      ) : null}
      {editor.info ? (
        <p className='rounded-lg bg-sky-50 px-4 py-3 text-sm text-sky-700'>
          {editor.info}
        </p>
      ) : null}

      {filteredSections.includes('branding') ? (
        <BillingBrandingSection
          editor={editor}
          editable={canEditBranding}
          embedded={embedded}
        />
      ) : null}

      {filteredSections.includes('custom_domain') ? (
        <BillingDomainSection
          editor={editor}
          editable={canEditDomain}
          actionable={data.capabilities.custom_domain}
          embedded={embedded}
        />
      ) : null}

      {filteredSections.includes('custom_wechat') ? (
        <BillingIntegrationSection
          editor={editor}
          provider='wechat_oauth'
          editable={canEditWechat}
          actionable={data.capabilities.custom_wechat}
          embedded={embedded}
        />
      ) : null}

      {filteredSections.includes('custom_payment') ? (
        <div className='space-y-4'>
          <BillingPaymentProviderSelector
            selectedProviders={selectedPaymentProviders}
            onSelectedProvidersChange={setSelectedPaymentProviders}
          />
          {selectedPaymentProviders.map(provider => (
            <BillingIntegrationSection
              key={provider}
              editor={editor}
              provider={provider}
              editable={canEditPayment}
              actionable={data.capabilities.custom_payment}
              embedded={embedded}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function useBillingCustomizationEditorState({
  creatorBid,
  disabled,
}: {
  creatorBid?: string;
  disabled?: boolean;
}): BillingCustomizationEditorState {
  const { t } = useTranslation();
  const { mutate: mutateCache } = useSWRConfig();
  const isAdminMode = Boolean(creatorBid);
  const swrKey = disabled
    ? null
    : isAdminMode
      ? buildBillingSwrKey('admin-billing-customization', creatorBid)
      : buildBillingSwrKey('billing-customization');
  const { data, isLoading, mutate } = useSWR<BillingCustomization>(
    swrKey,
    async () =>
      isAdminMode
        ? ((await api.getAdminBillingCustomization(
            { creator_bid: creatorBid },
            BILLING_PASSIVE_REQUEST_CONFIG,
          )) as BillingCustomization)
        : ((await api.getBillingCustomization(
            {},
            BILLING_PASSIVE_REQUEST_CONFIG,
          )) as BillingCustomization),
    {
      revalidateOnFocus: false,
    },
  );
  const [wideLogo, setWideLogo] = React.useState('');
  const [squareLogo, setSquareLogo] = React.useState('');
  const [wideLogoPreview, setWideLogoPreview] = React.useState('');
  const [squareLogoPreview, setSquareLogoPreview] = React.useState('');
  const [domain, setDomain] = React.useState('');
  const [saving, setSaving] = React.useState('');
  const [error, setError] = React.useState('');
  const [info, setInfo] = React.useState('');
  const previewUrlsRef = React.useRef<{
    wide: string | null;
    square: string | null;
  }>({
    wide: null,
    square: null,
  });

  const replacePreviewUrl = React.useCallback(
    (target: 'wide' | 'square', nextUrl: string) => {
      const previous = previewUrlsRef.current[target];
      if (previous?.startsWith('blob:') && previous !== nextUrl) {
        URL.revokeObjectURL(previous);
      }
      previewUrlsRef.current[target] = nextUrl.startsWith('blob:')
        ? nextUrl
        : null;
      if (target === 'wide') {
        setWideLogoPreview(nextUrl);
        return;
      }
      setSquareLogoPreview(nextUrl);
    },
    [],
  );

  const latestDomainHost = data?.domains.items[0]?.host || '';
  React.useEffect(() => {
    setDomain(latestDomainHost);
  }, [latestDomainHost]);

  React.useEffect(() => {
    setWideLogo(data?.branding.logo_wide_url || '');
    setSquareLogo(data?.branding.logo_square_url || '');
    if (!previewUrlsRef.current.wide) {
      setWideLogoPreview(data?.branding.logo_wide_url || '');
    }
    if (!previewUrlsRef.current.square) {
      setSquareLogoPreview(data?.branding.logo_square_url || '');
    }
  }, [data?.branding.logo_square_url, data?.branding.logo_wide_url]);

  React.useEffect(
    () => () => {
      const previews = Object.values(previewUrlsRef.current);
      for (const preview of previews) {
        if (preview?.startsWith('blob:')) {
          URL.revokeObjectURL(preview);
        }
      }
    },
    [],
  );

  const run = React.useCallback(
    async (key: string, action: () => Promise<unknown>) => {
      setSaving(key);
      setError('');
      try {
        await action();
        await mutate();
        if (isAdminMode) {
          await mutateCache(
            cacheKey =>
              (Array.isArray(cacheKey) &&
                typeof cacheKey[0] === 'string' &&
                cacheKey[0].startsWith('admin-billing-customization')) ||
              (typeof cacheKey === 'string' &&
                cacheKey.startsWith('admin-billing-customization')),
            undefined,
            { revalidate: true },
          );
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        setSaving('');
      }
    },
    [isAdminMode, mutate, mutateCache],
  );

  const uploadLogo = React.useCallback(
    async (target: 'wide' | 'square', file?: File) => {
      if (!file) return;
      if (
        !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) ||
        file.size > 2 * 1024 * 1024
      ) {
        setError(t('module.billing.customization.branding.invalidFile'));
        return;
      }
      const dimensions = await readImageDimensions(file);
      if (dimensions) {
        const offSpec =
          target === 'square'
            ? dimensions.width < 32 ||
              dimensions.height < 32 ||
              dimensions.width !== dimensions.height
            : dimensions.height < 32 ||
              dimensions.width / dimensions.height > 220 / 32;
        setInfo(
          offSpec
            ? t('module.billing.customization.branding.resizeNotice')
            : '',
        );
      } else {
        setInfo('');
      }

      const localPreviewUrl = URL.createObjectURL(file);
      replacePreviewUrl(target, localPreviewUrl);

      await run(`logo-${target}`, async () => {
        const { uploadFile } = await import('@/lib/file');
        const response = await uploadFile(
          file,
          isAdminMode
            ? `/api/admin/billing/customization/${creatorBid}/branding/logo`
            : '/api/billing/customization/branding/logo',
          { target },
        );
        const payload = await response.json();
        if (!response.ok || payload.code !== 0) {
          throw new Error(
            payload.message ||
              t('module.billing.customization.branding.uploadFailed'),
          );
        }

        const uploadedUrl = String(payload.data || '');
        const nextWideLogo = target === 'wide' ? uploadedUrl : wideLogo;
        const nextSquareLogo = target === 'square' ? uploadedUrl : squareLogo;

        setWideLogo(nextWideLogo);
        setSquareLogo(nextSquareLogo);

        if (isAdminMode) {
          await api.updateAdminBillingCustomizationBranding({
            creator_bid: creatorBid,
            logo_wide_url: nextWideLogo,
            logo_square_url: nextSquareLogo,
          });
          return;
        }

        await api.updateBillingBranding({
          logo_wide_url: nextWideLogo,
          logo_square_url: nextSquareLogo,
        });
      });
    },
    [creatorBid, isAdminMode, replacePreviewUrl, run, squareLogo, t, wideLogo],
  );

  return {
    creatorBid,
    data: data || null,
    domain,
    error,
    info,
    isAdminMode,
    isLoading,
    run,
    saving,
    setDomain,
    setSquareLogoPreview: preview => replacePreviewUrl('square', preview),
    setSquareLogo,
    setWideLogoPreview: preview => replacePreviewUrl('wide', preview),
    setWideLogo,
    squareLogoPreview,
    squareLogo,
    uploadLogo,
    wideLogoPreview,
    wideLogo,
  };
}

function BillingSectionShell({
  title,
  description,
  embedded,
  children,
}: {
  title: string;
  description?: string;
  embedded?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={
        embedded
          ? 'space-y-3'
          : 'rounded-xl border border-gray-200 bg-white p-6'
      }
    >
      <div className={embedded ? 'space-y-1 px-1' : ''}>
        <h2
          className={
            embedded
              ? 'text-sm font-semibold text-slate-900'
              : 'text-lg font-semibold'
          }
        >
          {title}
        </h2>
        {description ? (
          <p className='text-sm leading-6 text-slate-500'>{description}</p>
        ) : null}
      </div>
      <div className={embedded ? '' : 'mt-4'}>{children}</div>
    </section>
  );
}

function BillingBrandingSection({
  editor,
  editable,
  embedded,
}: {
  editor: BillingCustomizationEditorState;
  editable: boolean;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const { creatorBid, data, isAdminMode, run, squareLogo, wideLogo } = editor;
  const hydratedRef = React.useRef(false);
  const lastSubmittedRef = React.useRef({
    wideLogo: '',
    squareLogo: '',
  });

  React.useEffect(() => {
    if (!data) {
      return;
    }
    lastSubmittedRef.current = {
      wideLogo: data.branding.logo_wide_url || '',
      squareLogo: data.branding.logo_square_url || '',
    };
    hydratedRef.current = false;
  }, [data]);

  React.useEffect(() => {
    if (!data || !embedded || !editable) {
      return;
    }
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      return;
    }
    if (
      wideLogo === lastSubmittedRef.current.wideLogo &&
      squareLogo === lastSubmittedRef.current.squareLogo
    ) {
      return;
    }

    const timer = window.setTimeout(() => {
      lastSubmittedRef.current = {
        wideLogo,
        squareLogo,
      };
      void run('branding', () =>
        isAdminMode
          ? api.updateAdminBillingCustomizationBranding({
              creator_bid: creatorBid,
              logo_wide_url: wideLogo,
              logo_square_url: squareLogo,
            })
          : api.updateBillingBranding({
              logo_wide_url: wideLogo,
              logo_square_url: squareLogo,
            }),
      );
    }, 450);

    return () => window.clearTimeout(timer);
  }, [
    data,
    creatorBid,
    editable,
    embedded,
    isAdminMode,
    run,
    squareLogo,
    wideLogo,
  ]);

  if (!data) return null;

  return (
    <BillingSectionShell
      title={t('module.billing.customization.branding.title')}
      embedded={embedded}
    >
      {!editable ? (
        <LockedNotice />
      ) : (
        <div className='space-y-4'>
          <div className='grid gap-4 md:grid-cols-2'>
            <LogoUploadField
              embedded={embedded}
              shape='wide'
              label={t('module.billing.customization.branding.wideLogo')}
              hint={t('module.billing.customization.branding.wideHint')}
              uploadLabel={t(
                'module.billing.customization.branding.uploadWide',
              )}
              previewUrl={editor.wideLogoPreview}
              value={editor.wideLogo}
              onChange={value => {
                editor.setWideLogo(value);
                editor.setWideLogoPreview(value);
              }}
              onUpload={file => editor.uploadLogo('wide', file)}
            />
            <LogoUploadField
              embedded={embedded}
              shape='square'
              label={t('module.billing.customization.branding.squareLogo')}
              hint={t('module.billing.customization.branding.squareHint')}
              uploadLabel={t(
                'module.billing.customization.branding.uploadSquare',
              )}
              previewUrl={editor.squareLogoPreview}
              value={editor.squareLogo}
              onChange={value => {
                editor.setSquareLogo(value);
                editor.setSquareLogoPreview(value);
              }}
              onUpload={file => editor.uploadLogo('square', file)}
            />
          </div>
          {!embedded ? (
            <Button
              type='button'
              disabled={editor.saving === 'branding'}
              onClick={() =>
                editor.run('branding', () =>
                  editor.isAdminMode
                    ? api.updateAdminBillingCustomizationBranding({
                        creator_bid: editor.creatorBid,
                        logo_wide_url: editor.wideLogo,
                        logo_square_url: editor.squareLogo,
                      })
                    : api.updateBillingBranding({
                        logo_wide_url: editor.wideLogo,
                        logo_square_url: editor.squareLogo,
                      }),
                )
              }
            >
              {t('module.billing.customization.actions.saveConfiguration')}
            </Button>
          ) : null}
        </div>
      )}
    </BillingSectionShell>
  );
}

function BillingDomainSection({
  editor,
  editable,
  actionable = editable,
  embedded,
}: {
  editor: BillingCustomizationEditorState;
  editable: boolean;
  actionable?: boolean;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const { data } = editor;
  if (!data) return null;

  return (
    <BillingSectionShell
      title={t('module.billing.customization.domain.title')}
      embedded={embedded}
    >
      {!editable ? (
        <LockedNotice />
      ) : (
        <div className='space-y-4'>
          {!actionable ? <PendingActivationNotice /> : null}
          <div className='flex flex-col gap-3 md:flex-row'>
            <input
              className='min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm'
              value={editor.domain}
              onChange={event => editor.setDomain(event.target.value)}
              placeholder={t('module.billing.customization.domain.placeholder')}
            />
            <Button
              type='button'
              className='md:self-start'
              disabled={!actionable || editor.saving === 'domain'}
              onClick={() =>
                editor.run('domain', () =>
                  editor.isAdminMode
                    ? api.createAdminBillingCustomizationDomain({
                        creator_bid: editor.creatorBid,
                        host: editor.domain,
                      })
                    : api.createBillingDomain({ host: editor.domain }),
                )
              }
            >
              {t('module.billing.customization.domain.bind')}
            </Button>
          </div>
          {data.domains.items.map(item => (
            <DomainBindingCard
              key={item.domain_binding_bid}
              editor={editor}
              item={item}
            />
          ))}
        </div>
      )}
    </BillingSectionShell>
  );
}

function BillingPaymentProviderSelector({
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
        {VISIBLE_PAYMENT_CUSTOMIZATION_PROVIDERS.map(provider => {
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

function BillingIntegrationSection({
  editor,
  provider,
  editable,
  actionable = editable,
  embedded,
}: {
  editor: BillingCustomizationEditorState;
  provider: BillingCustomizationProvider;
  editable: boolean;
  actionable?: boolean;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const { data } = editor;
  if (!data) return null;

  const integration = data.integrations.find(
    item => item.provider === provider,
  );
  if (!integration) {
    return null;
  }

  return (
    <BillingSectionShell
      title={t(`module.billing.customization.providers.${provider}`)}
      embedded={embedded}
    >
      {!actionable && editable ? <PendingActivationNotice /> : null}
      <IntegrationCard
        integration={integration}
        creatorBid={editor.creatorBid}
        isAdminMode={editor.isAdminMode}
        locked={!editable}
        actionDisabled={!actionable}
        saving={editor.saving === integration.provider}
        compact
        run={action => editor.run(integration.provider, action)}
      />
    </BillingSectionShell>
  );
}

function LogoUploadField({
  embedded,
  hint,
  label,
  onChange,
  onUpload,
  previewUrl,
  shape = 'wide',
  uploadLabel,
  value,
}: {
  embedded?: boolean;
  hint: string;
  label: string;
  onChange: (value: string) => void;
  onUpload: (file?: File) => void;
  previewUrl: string;
  shape?: 'wide' | 'square';
  uploadLabel: string;
  value: string;
}) {
  const { t } = useTranslation();
  const inputId = React.useId();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  return (
    <div
      className={
        embedded
          ? 'flex h-full flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm'
          : 'flex h-full flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4'
      }
    >
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
        ref={fileInputRef}
        type='file'
        accept='image/png,image/jpeg,image/webp'
        className='hidden'
        onChange={event => {
          void onUpload(event.target.files?.[0]);
          event.currentTarget.value = '';
        }}
      />
      <label
        htmlFor={inputId}
        className='sr-only'
      >
        {uploadLabel}
      </label>
      <input
        id={inputId}
        type='text'
        className='w-full rounded-lg border px-3 py-2 text-sm'
        value={value}
        placeholder={t('module.billing.customization.branding.urlPlaceholder')}
        onChange={event => onChange(event.target.value)}
      />
      <div className='mt-auto flex flex-wrap gap-2 pt-1'>
        <Button
          type='button'
          variant='outline'
          onClick={() => fileInputRef.current?.click()}
        >
          {uploadLabel}
        </Button>
        {previewUrl || value ? (
          <Button
            type='button'
            variant='ghost'
            onClick={() => onChange('')}
          >
            {t('module.billing.customization.actions.clear')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function DomainBindingCard({
  editor,
  item,
}: {
  editor: BillingCustomizationEditorState;
  item: BillingCustomization['domains']['items'][number];
}) {
  const { t } = useTranslation();

  const verificationError = String(
    item.metadata?.verification_error || item.metadata?.ssl_error || '',
  ).trim();

  return (
    <div className='rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-sm'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div className='min-w-0 space-y-1'>
          <strong className='block break-all text-base text-slate-950'>
            {item.host}
          </strong>
          <p className='text-xs text-slate-500'>
            {t('module.billing.customization.domain.verifyInstruction')}
          </p>
        </div>
        <div className='flex flex-wrap justify-end gap-2'>
          <span className='rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700'>
            {t(`module.billing.domains.status.${item.status}`)}
          </span>
          <span className='rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600'>
            {t(`module.billing.domains.ssl.${item.ssl_status}`)}
          </span>
        </div>
      </div>

      <div className='mt-4 rounded-lg border border-slate-200 bg-white p-3'>
        <div className='mb-2 text-xs font-medium text-slate-500'>
          {t('module.billing.customization.domain.dnsTitle')}
        </div>
        <dl className='grid gap-2 text-sm md:grid-cols-[120px_minmax(0,1fr)]'>
          <dt className='text-slate-500'>
            {t('module.billing.customization.domain.recordType')}
          </dt>
          <dd className='font-medium text-slate-900'>{DNS_TXT_RECORD_TYPE}</dd>
          <dt className='text-slate-500'>
            {t('module.billing.customization.domain.recordName')}
          </dt>
          <dd className='break-all font-mono text-slate-900'>
            {item.verification_record_name}
          </dd>
          <dt className='text-slate-500'>
            {t('module.billing.customization.domain.recordValue')}
          </dt>
          <dd className='break-all font-mono text-slate-900'>
            {item.verification_record_value}
          </dd>
        </dl>
      </div>

      {verificationError ? (
        <p className='mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700'>
          {t('module.billing.customization.domain.lastError', {
            reason: verificationError,
          })}
        </p>
      ) : null}

      <div className='mt-3 flex flex-wrap gap-2'>
        <Button
          type='button'
          variant='outline'
          disabled={editor.saving === 'domain'}
          onClick={() =>
            editor.run('domain', async () => {
              const nextItem = (await (editor.isAdminMode
                ? api.verifyAdminBillingCustomizationDomain({
                    creator_bid: editor.creatorBid,
                    domain_binding_bid: item.domain_binding_bid,
                  })
                : api.verifyBillingDomain({
                    domain_binding_bid: item.domain_binding_bid,
                  }))) as Partial<typeof item>;
              toast({
                title: t(
                  nextItem.status === 'verified'
                    ? 'module.billing.customization.domain.verifySuccess'
                    : 'module.billing.customization.domain.verifyFailed',
                ),
              });
            })
          }
        >
          {t('module.billing.customization.domain.verify')}
        </Button>
        <Button
          type='button'
          variant='outline'
          disabled={editor.saving === 'domain'}
          onClick={() =>
            editor.run('domain', async () => {
              await (editor.isAdminMode
                ? api.disableAdminBillingCustomizationDomain({
                    creator_bid: editor.creatorBid,
                    domain_binding_bid: item.domain_binding_bid,
                  })
                : api.disableBillingDomain({
                    domain_binding_bid: item.domain_binding_bid,
                  }));
              toast({
                title: t('module.billing.customization.domain.disableSuccess'),
              });
            })
          }
        >
          {t('module.billing.customization.disable')}
        </Button>
      </div>
    </div>
  );
}

async function readImageDimensions(
  file: File,
): Promise<{ width: number; height: number } | null> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const result = await new Promise<{ width: number; height: number } | null>(
      resolve => {
        const image = new Image();
        image.onload = () =>
          resolve({
            width: image.naturalWidth,
            height: image.naturalHeight,
          });
        image.onerror = () => resolve(null);
        image.src = objectUrl;
      },
    );
    return result;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function IntegrationCard({
  integration,
  creatorBid,
  isAdminMode,
  locked,
  actionDisabled = false,
  saving,
  compact = false,
  run,
}: {
  integration: BillingCustomizationIntegration;
  creatorBid?: string;
  isAdminMode: boolean;
  locked: boolean;
  actionDisabled?: boolean;
  saving: boolean;
  compact?: boolean;
  run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const fields = PROVIDER_FIELDS[integration.provider];
  const [publicConfig, setPublicConfig] = React.useState<
    Record<string, string>
  >({});
  const [secretConfig, setSecretConfig] = React.useState<
    Record<string, string>
  >({});
  const integrationResetKey = `${integration.provider}:${integration.integration_bid || ''}:${integration.status}`;

  React.useEffect(() => {
    setPublicConfig(
      Object.fromEntries(
        Object.entries(integration.public_config || {}).map(([key, value]) => [
          key,
          String(value ?? ''),
        ]),
      ),
    );
    setSecretConfig({});
    // Reset form state only when switching integration identity/status; unrelated
    // refetches must not wipe in-progress credential input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [integrationResetKey]);

  const saveIntegration = React.useCallback(async () => {
    await (isAdminMode
      ? api.saveAdminBillingCustomizationIntegration({
          creator_bid: creatorBid,
          provider: integration.provider,
          public_config: publicConfig,
          secret_config: secretConfig,
        })
      : api.saveBillingIntegration({
          provider: integration.provider,
          public_config: publicConfig,
          secret_config: secretConfig,
        }));
  }, [
    creatorBid,
    integration.provider,
    isAdminMode,
    publicConfig,
    secretConfig,
  ]);

  return (
    <div
      className={
        compact
          ? 'rounded-xl border border-slate-200 bg-white p-4 shadow-sm'
          : 'rounded-xl border border-gray-200 bg-white p-6'
      }
    >
      <div className='flex items-center justify-between gap-3'>
        <div className='font-semibold'>
          {t(`module.billing.customization.providers.${integration.provider}`)}
        </div>
        <span className='rounded-full bg-gray-100 px-3 py-1 text-xs'>
          {t(
            `module.billing.customization.integrationStatus.${integration.status}`,
          )}
        </span>
      </div>
      {locked ? (
        <div className='mt-4'>
          <LockedNotice />
        </div>
      ) : (
        <div className='mt-4 space-y-4'>
          <div className='grid gap-3 md:grid-cols-2'>
            {fields.public.map(field => (
              <ConfigInput
                key={field}
                label={field}
                value={publicConfig[field] || ''}
                onChange={value =>
                  setPublicConfig(current => ({ ...current, [field]: value }))
                }
              />
            ))}
            {fields.secret.map(field => (
              <ConfigInput
                key={field}
                label={field}
                value={secretConfig[field] || ''}
                onChange={value =>
                  setSecretConfig(current => ({ ...current, [field]: value }))
                }
                secret
              />
            ))}
          </div>
          {integration.callback_url ? (
            <p className='break-all rounded bg-gray-50 p-3 text-xs text-gray-600'>
              {integration.callback_url}
            </p>
          ) : null}
          {integration.last_error_message ? (
            <p className='text-sm text-red-600'>
              {integration.last_error_message}
            </p>
          ) : null}
          <div className='flex flex-wrap gap-2'>
            <Button
              type='button'
              disabled={saving || actionDisabled}
              onClick={() => run(saveIntegration)}
            >
              {t('module.billing.customization.actions.saveIntegration')}
            </Button>
            {integration.integration_bid &&
            integration.status !== 'verified' ? (
              <Button
                type='button'
                variant='outline'
                disabled={saving || actionDisabled}
                onClick={() =>
                  run(() =>
                    isAdminMode
                      ? api.verifyAdminBillingCustomizationIntegration({
                          creator_bid: creatorBid,
                          provider: integration.provider,
                          integration_bid: integration.integration_bid,
                        })
                      : api.verifyBillingIntegration({
                          provider: integration.provider,
                          integration_bid: integration.integration_bid,
                        }),
                  )
                }
              >
                {t('module.billing.customization.verify')}
              </Button>
            ) : null}
            {integration.status === 'verified' ? (
              <Button
                type='button'
                variant='outline'
                disabled={saving || actionDisabled}
                onClick={() =>
                  run(() =>
                    isAdminMode
                      ? api.disableAdminBillingCustomizationIntegration({
                          creator_bid: creatorBid,
                          provider: integration.provider,
                        })
                      : api.disableBillingIntegration({
                          provider: integration.provider,
                        }),
                  )
                }
              >
                {t('module.billing.customization.disable')}
              </Button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfigInput({
  label,
  value,
  onChange,
  secret = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secret?: boolean;
}) {
  const multiline = secret && (label.includes('key') || label.includes('cert'));
  return (
    <label className='block text-sm'>
      <span className='mb-1 block text-gray-600'>{label}</span>
      {multiline ? (
        <textarea
          rows={4}
          className='w-full rounded-lg border px-3 py-2 font-mono text-xs'
          value={value}
          onChange={event => onChange(event.target.value)}
          autoComplete='new-password'
        />
      ) : (
        <input
          type={secret ? 'password' : 'text'}
          className='w-full rounded-lg border px-3 py-2'
          value={value}
          onChange={event => onChange(event.target.value)}
          autoComplete={secret ? 'new-password' : 'off'}
        />
      )}
    </label>
  );
}
