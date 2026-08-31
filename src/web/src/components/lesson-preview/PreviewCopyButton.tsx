'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy } from 'lucide-react';
import { copyText } from '@/c-utils/textutils';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface PreviewCopyButtonProps {
  /** Raw LLM-generated content of the element (markdown for text, HTML for view). */
  content: string;
}

const COPIED_RESET_MS = 1800;

/**
 * MarkdownFlow verbatim-block fence. The copied content is wrapped with this
 * marker on its own line above and below so the result can be pasted directly
 * into MarkdownFlow.
 */
const MARKDOWNFLOW_FENCE = '!===';

/**
 * Copy button rendered under each generated element in the debug preview.
 * Copies the element's raw LLM output to the clipboard wrapped in MarkdownFlow
 * `!===` fences so the result is ready to paste into MarkdownFlow.
 */
const PreviewCopyButton: React.FC<PreviewCopyButtonProps> = ({ content }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const resetTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  React.useEffect(
    () => () => {
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current);
      }
    },
    [],
  );

  const handleCopy = React.useCallback(async () => {
    if (!content) return;
    const wrapped = `${MARKDOWNFLOW_FENCE}\n${content.trim()}\n${MARKDOWNFLOW_FENCE}`;
    await copyText(wrapped);
    setCopied(true);
    if (resetTimerRef.current) {
      clearTimeout(resetTimerRef.current);
    }
    resetTimerRef.current = setTimeout(() => setCopied(false), COPIED_RESET_MS);
  }, [content]);

  if (!content) {
    return null;
  }

  return (
    <div className='flex justify-end mt-2'>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type='button'
            onClick={handleCopy}
            className={cn(
              'inline-flex items-center justify-center gap-1',
              'rounded-full px-2.5 py-1 text-xs font-medium text-white',
              'bg-[#55575e] transition-colors hover:bg-primary',
            )}
          >
            {copied ? (
              <Check className='h-3.5 w-3.5' />
            ) : (
              <Copy className='h-3.5 w-3.5' />
            )}
            <span>
              {copied
                ? t('module.shifu.previewArea.copied')
                : t('module.shifu.previewArea.copy')}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent className='max-w-[220px] text-center'>
          {t('module.shifu.previewArea.copyTooltip')}
        </TooltipContent>
      </Tooltip>
    </div>
  );
};

export default PreviewCopyButton;
