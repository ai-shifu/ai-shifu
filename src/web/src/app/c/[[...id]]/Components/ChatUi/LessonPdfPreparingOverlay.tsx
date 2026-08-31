import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function LessonPdfPreparingOverlay() {
  const { t } = useTranslation();
  const overlayRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const activeElement = document.activeElement as HTMLElement | null;
    const printPage = document.querySelector<HTMLElement>(
      '[data-lesson-print-page="true"]',
    );
    const hadInert = printPage?.hasAttribute('inert') ?? false;
    const previousAriaHidden = printPage?.getAttribute('aria-hidden') ?? null;

    printPage?.setAttribute('inert', '');
    printPage?.setAttribute('aria-hidden', 'true');
    overlayRef.current?.focus();

    return () => {
      if (printPage) {
        if (!hadInert) {
          printPage.removeAttribute('inert');
        }
        if (previousAriaHidden === null) {
          printPage.removeAttribute('aria-hidden');
        } else {
          printPage.setAttribute('aria-hidden', previousAriaHidden);
        }
      }
      if (activeElement?.isConnected) {
        activeElement.focus();
      }
    };
  }, []);

  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <div
      ref={overlayRef}
      data-lesson-print-exclude='true'
      className='fixed inset-0 z-[2000] flex items-center justify-center bg-background/90 backdrop-blur-sm'
      role='dialog'
      aria-modal='true'
      aria-label={t('module.chat.lessonPdfPreparing')}
      tabIndex={-1}
    >
      <div className='flex items-center gap-3 rounded-xl border border-border bg-card px-5 py-4 text-sm font-medium text-foreground shadow-lg'>
        <Loader2
          className='h-5 w-5 animate-spin text-primary'
          aria-hidden='true'
        />
        {t('module.chat.lessonPdfPreparing')}
      </div>
    </div>,
    document.body,
  );
}
