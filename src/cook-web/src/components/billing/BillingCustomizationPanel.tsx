'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useBillingCustomization } from '@/hooks/useBillingData';
import type {
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
    public: ['app_id', 'gateway_url'],
    secret: ['app_private_key', 'alipay_public_key'],
  },
  wechatpay: {
    public: ['app_id', 'mch_id', 'merchant_serial_no', 'base_url'],
    secret: ['api_v3_key', 'private_key', 'platform_cert'],
  },
};

function LockedNotice() {
  const { t } = useTranslation();
  return (
    <p className='rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800'>
      {t('module.billing.customization.locked')}
    </p>
  );
}

export function BillingCustomizationPanel() {
  const { t } = useTranslation();
  const { data, isLoading, mutate } = useBillingCustomization();
  const [wideLogo, setWideLogo] = React.useState('');
  const [squareLogo, setSquareLogo] = React.useState('');
  const [domain, setDomain] = React.useState('');
  const [saving, setSaving] = React.useState('');
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    setWideLogo(data?.branding.logo_wide_url || '');
    setSquareLogo(data?.branding.logo_square_url || '');
  }, [data?.branding.logo_square_url, data?.branding.logo_wide_url]);

  if (isLoading || !data) {
    return (
      <div className='py-12 text-center text-sm text-gray-500'>
        {t('common.loading')}
      </div>
    );
  }

  const run = async (key: string, action: () => Promise<unknown>) => {
    setSaving(key);
    setError('');
    try {
      await action();
      await mutate();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving('');
    }
  };

  const uploadLogo = async (target: 'wide' | 'square', file?: File) => {
    if (!file) return;
    if (
      !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) ||
      file.size > 2 * 1024 * 1024
    ) {
      setError(t('module.billing.customization.branding.invalidFile'));
      return;
    }
    await run(`logo-${target}`, async () => {
      const { uploadFile } = await import('@/lib/file');
      const response = await uploadFile(
        file,
        '/api/billing/customization/branding/logo',
      );
      const payload = await response.json();
      if (!response.ok || payload.code !== 0)
        throw new Error(payload.message || 'upload failed');
      if (target === 'wide') setWideLogo(payload.data);
      else setSquareLogo(payload.data);
    });
  };

  return (
    <div
      className='space-y-8 pb-8'
      data-testid='billing-customization-panel'
    >
      {error && (
        <p
          role='alert'
          className='rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700'
        >
          {error}
        </p>
      )}
      <section className='rounded-xl border border-gray-200 bg-white p-6'>
        <h2 className='text-lg font-semibold'>
          {t('module.billing.customization.branding.title')}
        </h2>
        {!data.capabilities.branding ? (
          <LockedNotice />
        ) : (
          <div className='mt-4 grid gap-4 md:grid-cols-2'>
            <ConfigInput
              label={t('module.billing.customization.branding.wideLogo')}
              value={wideLogo}
              onChange={setWideLogo}
            />
            <ConfigInput
              label={t('module.billing.customization.branding.squareLogo')}
              value={squareLogo}
              onChange={setSquareLogo}
            />
            <label className='text-sm'>
              {t('module.billing.customization.branding.uploadWide')}
              <input
                className='mt-1 block'
                type='file'
                accept='image/png,image/jpeg,image/webp'
                onChange={event =>
                  void uploadLogo('wide', event.target.files?.[0])
                }
              />
            </label>
            <label className='text-sm'>
              {t('module.billing.customization.branding.uploadSquare')}
              <input
                className='mt-1 block'
                type='file'
                accept='image/png,image/jpeg,image/webp'
                onChange={event =>
                  void uploadLogo('square', event.target.files?.[0])
                }
              />
            </label>
            <button
              className='w-fit rounded-lg bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50'
              disabled={saving === 'branding'}
              onClick={() =>
                run('branding', () =>
                  api.updateBillingBranding({
                    logo_wide_url: wideLogo,
                    logo_square_url: squareLogo,
                  }),
                )
              }
            >
              {t('common.save')}
            </button>
          </div>
        )}
      </section>

      <section className='rounded-xl border border-gray-200 bg-white p-6'>
        <h2 className='text-lg font-semibold'>
          {t('module.billing.customization.domain.title')}
        </h2>
        {!data.capabilities.custom_domain ? (
          <LockedNotice />
        ) : (
          <div className='mt-4 space-y-4'>
            <div className='flex gap-3'>
              <input
                className='min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm'
                value={domain}
                onChange={event => setDomain(event.target.value)}
                placeholder='learn.example.com'
              />
              <button
                className='rounded-lg bg-gray-900 px-4 py-2 text-sm text-white'
                onClick={() =>
                  run('domain', () => api.createBillingDomain({ host: domain }))
                }
              >
                {t('module.billing.customization.domain.bind')}
              </button>
            </div>
            {data.domains.items.map(item => (
              <div
                key={item.domain_binding_bid}
                className='rounded-lg bg-gray-50 p-4 text-sm'
              >
                <div className='flex flex-wrap items-center justify-between gap-2'>
                  <strong>{item.host}</strong>
                  <span>
                    {t('module.billing.customization.domain.status', {
                      status: item.status,
                      sslStatus: item.ssl_status,
                    })}
                  </span>
                </div>
                <p className='mt-2 break-all text-gray-600'>
                  {t('module.billing.customization.domain.record', {
                    name: item.verification_record_name,
                    value: item.verification_record_value,
                  })}
                </p>
                <div className='mt-3 flex gap-2'>
                  <button
                    className='rounded border px-3 py-1.5'
                    onClick={() =>
                      run('domain', () =>
                        api.verifyBillingDomain({
                          domain_binding_bid: item.domain_binding_bid,
                        }),
                      )
                    }
                  >
                    {t('module.billing.customization.domain.verify')}
                  </button>
                  <button
                    className='rounded border px-3 py-1.5'
                    onClick={() =>
                      run('domain', () =>
                        api.disableBillingDomain({
                          domain_binding_bid: item.domain_binding_bid,
                        }),
                      )
                    }
                  >
                    {t('module.billing.customization.disable')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className='space-y-4'>
        <h2 className='text-lg font-semibold'>
          {t('module.billing.customization.integrations.title')}
        </h2>
        {data.integrations.map(integration => (
          <IntegrationCard
            key={integration.provider}
            integration={integration}
            locked={
              integration.provider === 'wechat_oauth'
                ? !data.capabilities.custom_wechat
                : !data.capabilities.custom_payment
            }
            saving={saving === integration.provider}
            run={action => run(integration.provider, action)}
          />
        ))}
      </section>
    </div>
  );
}

function IntegrationCard({
  integration,
  locked,
  saving,
  run,
}: {
  integration: BillingCustomizationIntegration;
  locked: boolean;
  saving: boolean;
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
  }, [integration]);

  return (
    <div className='rounded-xl border border-gray-200 bg-white p-6'>
      <div className='flex items-center justify-between gap-3'>
        <h3 className='font-semibold'>
          {t(`module.billing.customization.providers.${integration.provider}`)}
        </h3>
        <span className='rounded-full bg-gray-100 px-3 py-1 text-xs'>
          {integration.status}
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
          {integration.callback_url && (
            <p className='break-all rounded bg-gray-50 p-3 text-xs text-gray-600'>
              {integration.callback_url}
            </p>
          )}
          {integration.last_error_message && (
            <p className='text-sm text-red-600'>
              {integration.last_error_message}
            </p>
          )}
          <div className='flex flex-wrap gap-2'>
            <button
              disabled={saving}
              className='rounded-lg bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50'
              onClick={() =>
                run(() =>
                  api.saveBillingIntegration({
                    provider: integration.provider,
                    public_config: publicConfig,
                    secret_config: secretConfig,
                  }),
                )
              }
            >
              {t('common.save')}
            </button>
            {integration.integration_bid && (
              <button
                disabled={saving}
                className='rounded-lg border px-4 py-2 text-sm'
                onClick={() =>
                  run(() =>
                    api.verifyBillingIntegration({
                      provider: integration.provider,
                      integration_bid: integration.integration_bid,
                    }),
                  )
                }
              >
                {t('module.billing.customization.verify')}
              </button>
            )}
            {integration.status === 'verified' && (
              <button
                disabled={saving}
                className='rounded-lg border px-4 py-2 text-sm'
                onClick={() =>
                  run(() =>
                    api.disableBillingIntegration({
                      provider: integration.provider,
                    }),
                  )
                }
              >
                {t('module.billing.customization.disable')}
              </button>
            )}
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
