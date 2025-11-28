import React, { useState } from 'react';
import { Button } from '@/components/button';
import { Loader2, MonitorPlay, PlayIcon } from 'lucide-react';
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
      if(!currentShifu?.readonly){
        await actions.saveMdflow();
      }
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
    <div className='flex items-center justify-center h-9 rounded-lg cursor-pointer shifu-setting-icon-container ml-2'>
      <Button
        variant='ghost'
        size='sm'
        className='h-8 px-2 text-xs font-normal'
        onClick={handleStartPreview}
        disabled={loading}
        loading={loading}
      >
        {loading ? null : <MonitorPlay className='h-4 w-4 mr-[5px]' />}{' '}
        <span className='title'>{t('module.preview.previewAll')}</span>
      </Button>
    </div>
  );
};

export default PreviewSettingsModal;
