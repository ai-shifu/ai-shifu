import type { Dispatch, SetStateAction } from 'react';
import { Loader2, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import ModelList from '@/components/model-list';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import { FormLabel } from '@/components/ui/Form';
import { useToast } from '@/hooks/useToast';

type AskPreviewMeta = {
  provider: string;
  requestedProvider: string;
  fallbackUsed: boolean;
};

type AskProviderOption = {
  value: string;
  label: string;
};

type AskSettingsSectionProps = {
  readonly?: boolean;
  askProviderOptions: AskProviderOption[];
  resolvedAskProvider: string;
  askProviderLlmValue: string;
  askModel: string;
  onAskModelChange: (value: string) => void;
  askTemperature: number;
  askTemperatureInput: string;
  setAskTemperature: Dispatch<SetStateAction<number>>;
  setAskTemperatureInput: Dispatch<SetStateAction<string>>;
  normalizeAskTemperature: (value: number) => number;
  adjustAskTemperature: (delta: number) => void;
  onAskProviderChange: (value: string) => void;
  askProviderFieldEntries: Array<[string, any]>;
  askProviderRequiredFields: Set<string>;
  askProviderConfig: Record<string, any>;
  setAskProviderConfig: Dispatch<SetStateAction<Record<string, any>>>;
  askProviderObjectInputs: Record<string, string>;
  setAskProviderObjectInputs: Dispatch<SetStateAction<Record<string, string>>>;
  askPreviewLoading: boolean;
  askPreviewQuery: string;
  setAskPreviewQuery: Dispatch<SetStateAction<string>>;
  handleAskPreview: () => void;
  askPreviewMeta: AskPreviewMeta | null;
  askPreviewResult: string;
};

export default function AskSettingsSection({
  readonly,
  askProviderOptions,
  resolvedAskProvider,
  askProviderLlmValue,
  askModel,
  onAskModelChange,
  askTemperature,
  askTemperatureInput,
  setAskTemperature,
  setAskTemperatureInput,
  normalizeAskTemperature,
  adjustAskTemperature,
  onAskProviderChange,
  askProviderFieldEntries,
  askProviderRequiredFields,
  askProviderConfig,
  setAskProviderConfig,
  askProviderObjectInputs,
  setAskProviderObjectInputs,
  askPreviewLoading,
  askPreviewQuery,
  setAskPreviewQuery,
  handleAskPreview,
  askPreviewMeta,
  askPreviewResult,
}: AskSettingsSectionProps) {
  const { t } = useTranslation();
  const { toast } = useToast();

  return (
    <div className='mb-6'>
      <div className='space-y-2 mb-4'>
        <FormLabel className='text-sm font-medium text-foreground'>
          {t('module.shifuSetting.askTitle')}
        </FormLabel>
        <Select
          value={resolvedAskProvider}
          onValueChange={onAskProviderChange}
          disabled={readonly}
        >
          <SelectTrigger className='h-9'>
            <SelectValue
              placeholder={t('module.shifuSetting.askProviderSelect')}
            />
          </SelectTrigger>
          <SelectContent>
            {askProviderOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {resolvedAskProvider === askProviderLlmValue && (
          <div className='space-y-2 pt-2'>
            <FormLabel className='text-sm font-medium text-foreground'>
              {t('module.shifuSetting.askModel')}
            </FormLabel>
            <ModelList
              disabled={readonly}
              className='h-9'
              value={askModel}
              onChange={onAskModelChange}
            />

            <div className='space-y-2 pt-2'>
              <FormLabel className='text-sm font-medium text-foreground'>
                {t('module.shifuSetting.askTemperature')}
              </FormLabel>
              <p className='text-xs text-muted-foreground'>
                {t('module.shifuSetting.askTemperatureHint')}
              </p>
              <div className='flex items-center gap-2'>
                <Input
                  type='text'
                  inputMode='decimal'
                  value={askTemperatureInput}
                  onChange={e => setAskTemperatureInput(e.target.value)}
                  onBlur={() => {
                    const parsed = Number(askTemperatureInput);
                    const normalized = Number.isFinite(parsed)
                      ? normalizeAskTemperature(parsed)
                      : askTemperature;
                    setAskTemperature(normalized);
                    setAskTemperatureInput(String(normalized));
                  }}
                  disabled={readonly}
                  className='h-9 flex-1'
                />
                {!readonly && (
                  <div className='flex items-center gap-2'>
                    <Button
                      type='button'
                      variant='outline'
                      size='icon'
                      onClick={() => adjustAskTemperature(-0.1)}
                      className='h-9 w-9'
                    >
                      <Minus className='h-4 w-4' />
                    </Button>
                    <Button
                      type='button'
                      variant='outline'
                      size='icon'
                      onClick={() => adjustAskTemperature(0.1)}
                      className='h-9 w-9'
                    >
                      <Plus className='h-4 w-4' />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {askProviderFieldEntries.map(([fieldName, fieldSchema]) => {
        const schemaType = String((fieldSchema as any)?.type || 'string');
        const schemaFormat = String(
          (fieldSchema as any)?.format || '',
        ).toLowerCase();
        const fieldLabel = (fieldSchema as any)?.title || fieldName || '';
        const fieldHint = (fieldSchema as any)?.description || '';
        const isRequired = askProviderRequiredFields.has(fieldName);
        const displayLabel = isRequired ? `${fieldLabel} *` : fieldLabel;

        if (schemaType === 'object') {
          const rawValue =
            askProviderObjectInputs[fieldName] ??
            JSON.stringify(askProviderConfig[fieldName] ?? {}, null, 2);
          return (
            <div
              key={fieldName}
              className='space-y-2 mb-4'
            >
              <FormLabel className='text-sm font-medium text-foreground'>
                {displayLabel}
              </FormLabel>
              {fieldHint && (
                <p className='text-xs text-muted-foreground'>{fieldHint}</p>
              )}
              <Textarea
                disabled={readonly}
                value={rawValue}
                onChange={e =>
                  setAskProviderObjectInputs(prev => ({
                    ...prev,
                    [fieldName]: e.target.value,
                  }))
                }
                onBlur={() => {
                  const nextRaw =
                    askProviderObjectInputs[fieldName] ?? rawValue;
                  const trimmed = String(nextRaw || '').trim();
                  if (!trimmed) {
                    if (isRequired) {
                      toast({
                        title: t(
                          'module.shifuSetting.askProviderConfigRequired',
                          { field: fieldLabel },
                        ),
                        variant: 'destructive',
                      });
                    }
                    return;
                  }
                  try {
                    const parsed = JSON.parse(trimmed);
                    if (
                      !parsed ||
                      typeof parsed !== 'object' ||
                      Array.isArray(parsed)
                    ) {
                      throw new Error('invalid object');
                    }
                    setAskProviderConfig(prev => ({
                      ...prev,
                      [fieldName]: parsed,
                    }));
                  } catch {
                    toast({
                      title: t(
                        'module.shifuSetting.askProviderConfigInvalidJson',
                        { field: fieldLabel },
                      ),
                      variant: 'destructive',
                    });
                  }
                }}
                minRows={3}
                maxRows={12}
              />
            </div>
          );
        }

        const rawFieldValue = askProviderConfig[fieldName];
        if (schemaType === 'boolean') {
          return (
            <div
              key={fieldName}
              className='flex items-start justify-between mb-4'
            >
              <div className='space-y-1'>
                <FormLabel className='text-sm font-medium text-foreground'>
                  {displayLabel}
                </FormLabel>
                {fieldHint && (
                  <p className='text-xs text-muted-foreground'>{fieldHint}</p>
                )}
              </div>
              <Switch
                checked={Boolean(rawFieldValue)}
                onCheckedChange={value =>
                  setAskProviderConfig(prev => ({
                    ...prev,
                    [fieldName]: value,
                  }))
                }
                disabled={readonly}
              />
            </div>
          );
        }

        return (
          <div
            key={fieldName}
            className='space-y-2 mb-4'
          >
            <FormLabel className='text-sm font-medium text-foreground'>
              {displayLabel}
            </FormLabel>
            {fieldHint && (
              <p className='text-xs text-muted-foreground'>{fieldHint}</p>
            )}
            <Input
              type={
                schemaType === 'number' || schemaType === 'integer'
                  ? 'number'
                  : schemaFormat === 'password'
                    ? 'password'
                    : 'text'
              }
              value={rawFieldValue ?? ''}
              onChange={e =>
                setAskProviderConfig(prev => ({
                  ...prev,
                  [fieldName]: e.target.value,
                }))
              }
              disabled={readonly}
              className='h-9'
            />
          </div>
        );
      })}

      <div className='space-y-2 mb-4'>
        <FormLabel className='text-sm font-medium text-foreground'>
          {t('module.shifuSetting.askPreviewQuestion')}
        </FormLabel>
        <Input
          disabled={readonly || askPreviewLoading}
          value={askPreviewQuery}
          onChange={e => setAskPreviewQuery(e.target.value)}
          placeholder={t('module.shifuSetting.askPreviewQuestionPlaceholder')}
          className='h-9'
        />
      </div>

      <div className='pt-2'>
        <Button
          type='button'
          variant='outline'
          onClick={handleAskPreview}
          disabled={readonly || askPreviewLoading}
          className='w-full'
        >
          {askPreviewLoading ? (
            <>
              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
              {t('module.shifuSetting.askPreviewLoading')}
            </>
          ) : (
            t('module.shifuSetting.askPreview')
          )}
        </Button>
      </div>

      {askPreviewMeta && (
        <p className='mt-3 text-xs text-muted-foreground'>
          {askPreviewMeta.fallbackUsed
            ? t('module.shifuSetting.askPreviewUsedFallback', {
                provider: askPreviewMeta.requestedProvider,
              })
            : t('module.shifuSetting.askPreviewUsedProvider', {
                provider: askPreviewMeta.provider,
              })}
        </p>
      )}

      {askPreviewResult && (
        <div className='space-y-2 mt-3'>
          <FormLabel className='text-sm font-medium text-foreground'>
            {t('module.shifuSetting.askPreviewResult')}
          </FormLabel>
          <Textarea
            value={askPreviewResult}
            readOnly
            minRows={3}
            maxRows={12}
          />
        </div>
      )}
    </div>
  );
}
