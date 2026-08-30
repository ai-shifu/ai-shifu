'use client';

import React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
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
import { Label } from '@/components/ui/Label';
import { useTranslation } from 'react-i18next';
import {
  buildCreateRatePayload,
  canonicalizeRateIdentity,
  deriveCreditsPerUnit,
  getSuggestedRateModel,
  hasExactRateIdentity,
  isRateRowCreateSuggestion,
  isValidMultiplier,
  isValidProvider,
  isValidRateModel,
  normalizeMultiplierInput,
  type CreateRatePayload,
  type RateBaseline,
  type RateIdentity,
  type RateRow,
  type RateTab,
} from './rateConfig';

type RateCreateDialogProps = {
  open: boolean;
  usageType: RateTab;
  rows: RateRow[];
  baseline?: RateBaseline;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (
    payload: CreateRatePayload,
    identity: RateIdentity,
  ) => Promise<boolean>;
};

export default function RateCreateDialog({
  open,
  usageType,
  rows,
  baseline,
  pending,
  onOpenChange,
  onCreate,
}: RateCreateDialogProps) {
  const { t } = useTranslation(['module.operationsConfig', 'common.core']);
  const [provider, setProvider] = React.useState('');
  const [model, setModel] = React.useState('');
  const [multiplier, setMultiplier] = React.useState('');
  const [error, setError] = React.useState('');
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const submittingRef = React.useRef(false);

  const suggestionRows = React.useMemo(
    () => rows.filter(row => isRateRowCreateSuggestion(row, usageType)),
    [rows, usageType],
  );
  const providerSuggestions = React.useMemo(
    () =>
      Array.from(
        new Set(suggestionRows.map(row => row.provider.trim()).filter(Boolean)),
      ),
    [suggestionRows],
  );
  const modelSuggestionRows = React.useMemo(() => {
    const normalizedProvider = provider.trim();
    return normalizedProvider
      ? suggestionRows.filter(row => row.provider === normalizedProvider)
      : suggestionRows;
  }, [provider, suggestionRows]);
  const modelSuggestions = React.useMemo(
    () =>
      Array.from(
        new Set(modelSuggestionRows.map(getSuggestedRateModel).filter(Boolean)),
      ),
    [modelSuggestionRows],
  );

  React.useEffect(() => {
    if (!open) {
      return;
    }
    setProvider('');
    setModel('');
    setMultiplier('');
    setError('');
    setConfirmOpen(false);
    submittingRef.current = false;
  }, [open, usageType]);

  const identity = React.useMemo(
    () => canonicalizeRateIdentity(usageType, provider, model),
    [model, provider, usageType],
  );
  const typeLabel = usageType === 'llm' ? t('tabs.llm') : t('tabs.tts');
  const identityLabel =
    usageType === 'tts'
      ? `${identity.provider}/${identity.rateModel || t('create.defaultTier')}`
      : identity.model;

  const validate = React.useCallback(() => {
    if (!identity.provider) {
      return t('create.errors.providerRequired');
    }
    if (!isValidProvider(identity.provider)) {
      return t('create.errors.providerInvalid');
    }
    if (usageType === 'llm' && !identity.rateModel) {
      return t('create.errors.modelRequired');
    }
    if (!isValidRateModel(usageType, identity.rateModel)) {
      return t('create.errors.modelInvalid');
    }
    if (!isValidMultiplier(multiplier)) {
      return t('invalidMultiplier');
    }
    if (!baseline?.is_configured) {
      return t('baselineMissing');
    }
    if (deriveCreditsPerUnit({ usageType, multiplier, baseline }) == null) {
      return usageType === 'tts'
        ? t('create.errors.ttsFactorMissing')
        : t('invalidMultiplier');
    }
    if (hasExactRateIdentity(rows, identity)) {
      return t('create.errors.duplicate');
    }
    return '';
  }, [baseline, identity, multiplier, rows, t, usageType]);

  const requestConfirmation = React.useCallback(() => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError('');
    setConfirmOpen(true);
  }, [validate]);

  const confirmCreate = React.useCallback(async () => {
    if (submittingRef.current) {
      return;
    }
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      setConfirmOpen(false);
      return;
    }
    const creditsPerUnit = deriveCreditsPerUnit({
      usageType,
      multiplier,
      baseline,
    });
    if (creditsPerUnit == null) {
      return;
    }

    submittingRef.current = true;
    try {
      const created = await onCreate(
        buildCreateRatePayload({ identity, creditsPerUnit }),
        identity,
      );
      if (created) {
        setConfirmOpen(false);
        onOpenChange(false);
      } else {
        setConfirmOpen(false);
      }
    } finally {
      submittingRef.current = false;
    }
  }, [
    baseline,
    identity,
    multiplier,
    onCreate,
    onOpenChange,
    usageType,
    validate,
  ]);

  const handleModelChange = React.useCallback(
    (value: string) => {
      setModel(value);
      setError('');
      const matches = suggestionRows.filter(
        row => getSuggestedRateModel(row) === value,
      );
      if (matches.length === 1) {
        setProvider(matches[0].provider);
      }
    },
    [suggestionRows],
  );

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={nextOpen => {
          if (!pending) {
            onOpenChange(nextOpen);
          }
        }}
      >
        <DialogContent
          className='overflow-hidden p-0 gap-0 sm:max-w-[520px]'
          showClose={!pending}
          onEscapeKeyDown={event => {
            if (pending) {
              event.preventDefault();
            }
          }}
          onInteractOutside={event => {
            if (pending) {
              event.preventDefault();
            }
          }}
        >
          <DialogHeader className='border-b border-border px-6 pb-4 pt-6'>
            <DialogTitle>{t('create.title')}</DialogTitle>
            <DialogDescription className='leading-6'>
              {t('create.description', { type: typeLabel })}
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={event => {
              event.preventDefault();
              requestConfirmation();
            }}
          >
            <div className='space-y-5 px-6 py-5'>
              <div className='space-y-2'>
                <Label>{t('create.typeLabel')}</Label>
                <div className='rounded-md border bg-muted/30 px-3 py-2 text-sm font-medium text-foreground'>
                  {typeLabel}
                </div>
              </div>

              <div className='space-y-2'>
                <Label htmlFor={`create-rate-provider-${usageType}`}>
                  {t('fields.provider')}
                </Label>
                <Input
                  id={`create-rate-provider-${usageType}`}
                  list={`create-rate-provider-suggestions-${usageType}`}
                  value={provider}
                  maxLength={32}
                  autoComplete='off'
                  disabled={pending}
                  placeholder={t('create.providerPlaceholder')}
                  onChange={event => {
                    setProvider(event.target.value);
                    setError('');
                  }}
                />
                <datalist id={`create-rate-provider-suggestions-${usageType}`}>
                  {providerSuggestions.map(value => (
                    <option
                      key={value}
                      value={value}
                    />
                  ))}
                </datalist>
              </div>

              <div className='space-y-2'>
                <Label htmlFor={`create-rate-model-${usageType}`}>
                  {usageType === 'llm'
                    ? t('fields.model')
                    : t('fields.modelTier')}
                </Label>
                <Input
                  id={`create-rate-model-${usageType}`}
                  list={`create-rate-model-suggestions-${usageType}`}
                  value={model}
                  maxLength={usageType === 'llm' ? 133 : 100}
                  autoComplete='off'
                  disabled={pending}
                  placeholder={
                    usageType === 'llm'
                      ? t('create.modelPlaceholder')
                      : t('create.ttsModelPlaceholder')
                  }
                  onChange={event => handleModelChange(event.target.value)}
                />
                <datalist id={`create-rate-model-suggestions-${usageType}`}>
                  {modelSuggestions.map(value => (
                    <option
                      key={value}
                      value={value}
                    />
                  ))}
                </datalist>
                {usageType === 'tts' ? (
                  <p className='text-xs leading-5 text-muted-foreground'>
                    {t('create.ttsDefaultHint')}
                  </p>
                ) : null}
              </div>

              <div className='space-y-2'>
                <Label htmlFor={`create-rate-multiplier-${usageType}`}>
                  {usageType === 'tts'
                    ? t('fields.ttsMultiplier')
                    : t('fields.multiplier')}
                </Label>
                <div className='flex items-center gap-2'>
                  <Input
                    id={`create-rate-multiplier-${usageType}`}
                    type='text'
                    inputMode='decimal'
                    value={multiplier}
                    className='max-w-[160px]'
                    disabled={pending}
                    placeholder={t('create.multiplierPlaceholder')}
                    onChange={event => {
                      setMultiplier(
                        normalizeMultiplierInput(event.target.value),
                      );
                      setError('');
                    }}
                  />
                  <span className='select-none text-sm font-medium text-foreground'>
                    {t('fields.multiplierSuffix')}
                  </span>
                </div>
              </div>

              <div className='rounded-md border border-primary/20 bg-primary/5 px-3 py-2.5 text-sm leading-6 text-muted-foreground'>
                {t('create.doesNotEnable')}
              </div>

              {error ? (
                <p
                  className='text-sm text-destructive'
                  role='alert'
                >
                  {error}
                </p>
              ) : null}
            </div>

            <DialogFooter className='gap-2 border-t border-border bg-background px-6 py-4'>
              <Button
                type='button'
                variant='outline'
                disabled={pending}
                onClick={() => onOpenChange(false)}
              >
                {t('common.core:cancel')}
              </Button>
              <Button
                type='submit'
                disabled={pending}
              >
                {t('actions.continue')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={nextOpen => {
          if (!pending) {
            setConfirmOpen(nextOpen);
          }
        }}
      >
        <AlertDialogContent
          className='max-w-[440px]'
          onEscapeKeyDown={event => {
            if (pending) {
              event.preventDefault();
            }
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>{t('create.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription className='leading-6 text-foreground'>
              {t('create.confirmDescription', {
                type: typeLabel,
                identity: identityLabel,
                multiplier,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>
              {t('common.core:cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={pending}
              onClick={event => {
                event.preventDefault();
                void confirmCreate();
              }}
            >
              {pending ? t('actions.adding') : t('actions.confirmAdd')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
