import React, { useState } from 'react';
import { Button } from '@/components/button';
import { Loader2, PlayIcon } from 'lucide-react';
import { useShifu } from '@/store';
import api from '@/api';
import { useTranslation } from 'react-i18next';

const PreviewSettingsModal = () => {
  const { t } = useTranslation();
  const { currentShifu, actions } = useShifu();
  const [loading, setLoading] = useState(false);

  const handleStartPreview = async () => {
    if (loading) {
      return;
    }

    try {
      setLoading(true);
      await actions.saveMdflow();
      const result = await api.previewShifu({
        shifu_bid: currentShifu?.bid || '',
        skip: false,
        variables: {},
      });
      if (result) {
        window.open(result, '_blank');
      }
    } catch (error) {
      console.error('Preview failed:', error);
    } finally {
      setLoading(false);
    }
  };
  return (
    <Button
      variant='ghost'
      size='sm'
      className='h-8 px-2 text-xs font-normal'
      onClick={handleStartPreview}
      disabled={loading}
      loading={loading}
    >
      {loading ? null : (
        <PlayIcon className='h-4 w-4' />
      )}{' '}
      {t('module.preview.preview')}
    </Button>
  );
};

export default PreviewSettingsModal;
