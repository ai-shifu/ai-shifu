'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Loader2, AlertCircle } from 'lucide-react';

// Reuse ai-shifu's shadcn/ui components
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Label } from '@/components/ui/Label';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { Textarea } from '@/components/ui/Textarea';

// Reuse ai-shifu's useToast hook
import { fail, show } from '@/hooks/useToast';

// Use alert dialog for confirmation
import { useAlert } from '@/components/ui/UseAlert';

// Use unified Request system
import http from '@/lib/request';
import api from '@/api';

// Analytics tracking
import { useTracking } from '@/c-common/hooks/useTracking';

// MDF conversion response type
interface MdfConvertResponse {
  content_prompt: string;
  request_id: string;
  timestamp: string;
  metadata: {
    input_length: number;
    output_length?: number;
    language: string;
    user_id: string;
  };
}

// Support email address
const SUPPORT_EMAIL = 'hello@ai-shifu.com';

interface MdfConvertDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplyContent?: (contentPrompt: string) => void;
}

export function MdfConvertDialog({
  open,
  onOpenChange,
  onApplyContent,
}: MdfConvertDialogProps) {
  const { t, i18n } = useTranslation();
  const { showAlert } = useAlert();
  const { trackEvent } = useTracking();

  const [inputText, setInputText] = useState('');
  const [isConverting, setIsConverting] = useState(false);
  const [result, setResult] = useState<MdfConvertResponse | null>(null);
  const [isMdfApiConfigured, setIsMdfApiConfigured] = useState<boolean | null>(
    null,
  );
  const [isCheckingConfig, setIsCheckingConfig] = useState(false);

  // Determine language based on i18n
  const language = i18n.language === 'zh-CN' ? 'Chinese' : 'English';

  // Check MDF API configuration status
  const checkMdfApiConfig = async () => {
    setIsCheckingConfig(true);
    try {
      const response = await api.genMdfConfigStatus({});
      setIsMdfApiConfigured(response.configured);
    } catch (error) {
      console.error('Failed to check MDF API config:', error);
      setIsMdfApiConfigured(false);
    } finally {
      setIsCheckingConfig(false);
    }
  };

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setInputText('');
      setResult(null);
      setIsConverting(false);
      checkMdfApiConfig();
    }
  }, [open]);

  // Validate input
  const validateInput = (): string | null => {
    if (inputText.trim().length === 0) {
      return t('component.mdfConvert.textTooShort');
    }
    if (inputText.length > 10000) {
      return t('component.mdfConvert.textTooLong');
    }
    return null;
  };

  // Handle conversion
  const handleConvert = async () => {
    const validationError = validateInput();
    if (validationError) {
      fail(validationError);
      return;
    }

    const inputLength = inputText.trim().length;
    const startTime = Date.now();

    // Track convert button click
    trackEvent('creator_mdf_convert_click', {
      input_length: inputLength,
    });

    setIsConverting(true);
    try {
      const response = (await api.genMdfConvert({
        text: inputText.trim(),
        language: language,
        output_mode: 'content',
      })) as MdfConvertResponse;

      // Track successful conversion
      trackEvent('creator_mdf_convert_success', {
        input_length: inputLength,
        duration_ms: Date.now() - startTime,
      });

      setResult(response);
      show(t('component.mdfConvert.convertSuccess'));
    } catch (error: any) {
      // Track conversion error
      trackEvent('creator_mdf_convert_error', {
        input_length: inputLength,
      // The Request class already displays the error message,
      // so no extra handling is needed here to avoid duplicate alerts.
      // Request 类已经显示了错误消息
      // 这里不需要额外处理，避免重复提示
    } finally {
      setIsConverting(false);
    }
  };

  // Copy to clipboard
  const copyToClipboard = async (text: string) => {
    // Track copy button click
    trackEvent('creator_mdf_copy_click', {});

    try {
      await navigator.clipboard.writeText(text);
      show(t('component.mdfConvert.copySuccess'));
    } catch (error) {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        fail(t('component.mdfConvert.copyError'));
      } catch (err) {
        fail('Copy failed');
      } finally {
        document.body.removeChild(textArea);
      }
    }
  };

  // Apply to editor
  const handleApply = () => {
    if (!result || !onApplyContent) return;

    // Track apply button click
    trackEvent('creator_mdf_apply_click', {});

    // Show confirmation dialog before applying
    showAlert({
      title: t('component.mdfConvert.confirmApplyTitle'),
      description: t('component.mdfConvert.confirmApplyDescription'),
      confirmText: t('component.mdfConvert.confirmApplyButton'),
      cancelText: t('component.mdfConvert.cancelButton'),
      onConfirm: () => {
        onApplyContent(result.content_prompt);
        show(t('component.mdfConvert.applySuccess'));
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent
        className='w-[92vw] sm:max-w-[900px] h-[75vh] max-h-[75vh] flex flex-col p-0 overflow-hidden'
        onInteractOutside={e => e.preventDefault()}
      >
        <DialogHeader className='px-6 pt-4 pb-2 border-0'>
          <DialogTitle className='text-xl font-semibold tracking-tight flex items-center gap-2'>
            {t('component.mdfConvert.dialogTitle')}
            <Badge
              variant='default'
              className='text-[10px] px-1.5 py-0 font-medium'
            >
              Beta
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <div className='flex-1 flex flex-col overflow-hidden px-6 pb-6'>
          {!result ? (
            // Input Form
            <div className='flex-1 flex flex-col min-h-0'>
              {/* Persistent warning when MDF API is not configured */}
              {isMdfApiConfigured === false && (
                <div className='flex-shrink-0 mb-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md'>
                  <div className='flex items-start gap-2'>
                    <AlertCircle className='h-5 w-5 text-yellow-600 dark:text-yellow-500 flex-shrink-0 mt-0.5' />
                    <div className='flex-1 text-sm'>
                      <p className='text-yellow-700 dark:text-yellow-300'>
                        {t('component.mdfConvert.configWarningMessage')}
                        <a
                          href={`mailto:${SUPPORT_EMAIL}`}
                          className='text-yellow-900 dark:text-yellow-100 underline hover:text-yellow-950 dark:hover:text-yellow-50 font-medium'
                        >
                          {SUPPORT_EMAIL}
                        </a>
                      </p>
                    </div>
                  </div>
                </div>
              )}
              <div className='flex-shrink-0 flex items-center justify-between mb-1'>
                <Label
                  htmlFor='input-text'
                  className='text-sm font-medium'
                >
                  {t('component.mdfConvert.inputLabel')}
                </Label>
              </div>
              <Textarea
                id='input-text'
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                placeholder={t('component.mdfConvert.inputPlaceholder')}
                className='flex-1 min-h-0 resize-none rounded-md border border-slate-300/80 bg-background/90 p-4 focus-visible:ring-1 focus-visible:ring-primary/40'
                disabled={isConverting}
              />
              <div className='flex-shrink-0 flex items-center justify-end mt-1'>
                <div className='text-xs text-muted-foreground'>
                  {inputText.length} / 10,000
                </div>
              </div>
            </div>
          ) : (
            // Result Display
            <div className='flex-1 flex flex-col min-h-0'>
              <div className='flex-shrink-0 flex items-center justify-between mb-1'>
                <h3 className='text-sm font-medium text-foreground'>
                  {t('component.mdfConvert.contentPromptTitle')}
                </h3>
                <Button
                  variant='ghost'
                  size='sm'
                  onClick={() => copyToClipboard(result.content_prompt)}
                  className='h-8 px-2'
                >
                  <Copy className='h-3 w-3 mr-1' />
                  {t('component.mdfConvert.copyButton')}
                </Button>
              </div>
              <div className='flex-1 min-h-0 overflow-y-auto rounded-md border border-slate-300/80 bg-background/90 p-4'>
                <pre className='text-sm whitespace-pre-wrap break-words font-mono leading-relaxed text-foreground'>
                  {result.content_prompt}
                </pre>
              </div>
              <div className='flex-shrink-0 flex items-center justify-end mt-1'>
                {/* Placeholder for alignment */}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className='px-6 pb-6 pt-2 border-0'>
          {!result ? (
            // Convert Form Actions
            <div className='flex w-full flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between'>
              <Button
                variant='outline'
                onClick={() => {
                  trackEvent('creator_mdf_cancel_click', {
                    input_length: inputText.length,
                  });
                  onOpenChange(false);
                }}
              >
                {t('common.core.cancel')}
              </Button>
              <Button
                onClick={handleConvert}
                disabled={
                  isMdfApiConfigured === false ||
                  isCheckingConfig ||
                  isConverting ||
                  !inputText.trim()
                }
                className='flex items-center gap-2'
              >
                {isConverting && <Loader2 className='h-4 w-4 animate-spin' />}
                {isConverting
                  ? t('component.mdfConvert.converting')
                  : t('component.mdfConvert.convertButton')}
              </Button>
            </div>
          ) : (
            // Result Actions
            <div className='flex w-full flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between'>
              <Button
                variant='outline'
                onClick={() => {
                  trackEvent('creator_mdf_back_click', {});
                  setResult(null);
                }}
              >
                {t('component.mdfConvert.backButton')}
              </Button>
              <div className='flex gap-2'>
                <Button
                  variant='outline'
                  onClick={() => {
                    trackEvent('creator_mdf_close_click', {});
                    onOpenChange(false);
                  }}
                >
                  {t('common.core.close')}
                </Button>
                {onApplyContent && (
                  <Button onClick={handleApply}>
                    {t('component.mdfConvert.applyButton')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
