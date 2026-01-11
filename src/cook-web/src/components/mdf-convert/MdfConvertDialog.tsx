'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Loader2 } from 'lucide-react';

// Reuse ai-shifu's shadcn/ui components
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

// Use unified Request system
import http from '@/lib/request';

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

  const [inputText, setInputText] = useState('');
  const [isConverting, setIsConverting] = useState(false);
  const [result, setResult] = useState<MdfConvertResponse | null>(null);

  // Determine language based on i18n
  const language = i18n.language === 'zh-CN' ? 'Chinese' : 'English';

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setInputText('');
      setResult(null);
      setIsConverting(false);
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

    setIsConverting(true);
    try {
      const baseUrl =
        process.env.NEXT_PUBLIC_GEN_MDF_API_URL || 'http://localhost:8000';

      const response = (await http.post(`${baseUrl}/gen/mdf-convert`, {
        text: inputText.trim(),
        language: language,
        output_mode: 'content',
      })) as MdfConvertResponse;

      setResult(response);
      show(t('component.mdfConvert.convertSuccess'));
    } catch {
      // Request class already shows toast for errors, just show a generic message
      fail(t('component.mdfConvert.convertError'), 5000);
    } finally {
      setIsConverting(false);
    }
  };

  // Copy to clipboard
  const copyToClipboard = async (text: string) => {
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
        show(t('component.mdfConvert.copySuccess'));
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

    onApplyContent(result.content_prompt);
    show(t('component.mdfConvert.applySuccess'));
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[820px] w-[92vw] h-[80vh] sm:max-h-[620px] max-h-[90vh] flex flex-col p-0 overflow-hidden'>
        <DialogHeader className='px-6 pt-6 pb-4 border-0'>
          <DialogTitle className='text-xl font-semibold tracking-tight'>
            {t('component.mdfConvert.dialogTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className='flex-1 flex flex-col overflow-hidden px-6 pb-6'>
          {!result ? (
            // Input Form
            <div className='flex flex-col flex-1 space-y-2'>
              <Label
                htmlFor='input-text'
                className='text-sm font-medium'
              >
                {t('component.mdfConvert.inputLabel')}
              </Label>
              <Textarea
                id='input-text'
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                placeholder={t('component.mdfConvert.inputPlaceholder')}
                className='flex-1 min-h-[200px] resize-none border-slate-300/80 bg-background/90 focus-visible:ring-1 focus-visible:ring-primary/40'
                disabled={isConverting}
              />
              <div className='text-xs text-muted-foreground text-right'>
                {inputText.length} / 10,000
              </div>
            </div>
          ) : (
            // Result Display
            <ScrollArea className='flex-1'>
              <div className='space-y-4'>
                <div className='space-y-2'>
                  <div className='flex items-center justify-between'>
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
                  <div className='min-h-[400px] max-h-[400px] overflow-y-auto rounded-md border border-slate-300/80 bg-background/90 p-4'>
                    <pre className='text-sm whitespace-pre-wrap break-words font-mono leading-relaxed text-foreground'>
                      {result.content_prompt}
                    </pre>
                  </div>
                </div>

                {/* Metadata */}
                <div className='text-xs text-muted-foreground space-y-1'>
                  <div>Request ID: {result.request_id}</div>
                  {result.metadata.output_length && (
                    <div>
                      Input: {result.metadata.input_length} chars | Output:{' '}
                      {result.metadata.output_length} chars
                    </div>
                  )}
                </div>
              </div>
            </ScrollArea>
          )}
        </div>

        <DialogFooter className='px-6 pb-6 pt-2 border-0'>
          {!result ? (
            // Convert Form Actions
            <div className='flex w-full flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between'>
              <Button
                variant='outline'
                onClick={() => onOpenChange(false)}
              >
                {t('common.core.cancel')}
              </Button>
              <Button
                onClick={handleConvert}
                disabled={isConverting || !inputText.trim()}
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
                onClick={() => setResult(null)}
              >
                {t('component.mdfConvert.backButton')}
              </Button>
              <div className='flex gap-2'>
                <Button
                  variant='outline'
                  onClick={() => onOpenChange(false)}
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
