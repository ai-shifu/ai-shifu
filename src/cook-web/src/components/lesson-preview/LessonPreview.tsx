'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Loader2 } from 'lucide-react';

interface LessonPreviewProps {
  loading: boolean;
  errorMessage?: string | null;
}

const LessonPreview: React.FC<LessonPreviewProps> = ({
  loading,
  errorMessage,
}) => {
  const { t } = useTranslation();

  const renderContent = () => {
    if (loading) {
      return (
        <div className='flex flex-col items-center justify-center gap-2 p-6 text-xs text-muted-foreground'>
          <Loader2 className='h-6 w-6 animate-spin text-muted-foreground' />
          <span>{t('module.shifu.previewArea.loading')}</span>
        </div>
      );
    }

    return (
      <div className='flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-xs text-muted-foreground'>
        <FileText className='h-8 w-8 text-muted-foreground' />
        <span>{t('module.shifu.previewArea.empty')}</span>
      </div>
    );
  };

  return (
    <div className='flex h-full flex-col rounded-xl border bg-white p-6 text-sm'>
      <div className='flex flex-wrap items-baseline gap-2'>
        <h2 className='text-base font-semibold text-foreground'>
          {t('module.shifu.previewArea.title')}
        </h2>
        <p className='text-xs text-muted-foreground'>
          {t('module.shifu.previewArea.description')}
        </p>
      </div>
      <div className='mt-4 flex-1 overflow-hidden rounded-xl border bg-muted/30'>
        {renderContent()}
      </div>
      {errorMessage ? (
        <p className='mt-3 text-xs text-destructive'>{errorMessage}</p>
      ) : null}
    </div>
  );
};

export default LessonPreview;
