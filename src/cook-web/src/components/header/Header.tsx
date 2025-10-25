'use client';
import React, { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { useShifu } from '@/store';
import Loading from '../loading';
import { useAlert } from '@/components/ui/UseAlert';
import api from '@/api';
import { Home, CircleAlert, CircleCheck, TrendingUp } from 'lucide-react';
import Preivew from '@/components/preview';
import ShifuSetting from '@/components/shifu-setting';
import { useTranslation } from 'react-i18next';
const Header = () => {
  const { t } = useTranslation();
  const alert = useAlert();
  const router = useRouter();
  const [publishing, setPublishing] = useState(false);
  const { isSaving, lastSaveTime, currentShifu, error, actions } = useShifu();
  const onShifuSave = async () => {
    if (currentShifu) {
      await actions.loadShifu(currentShifu.bid);
    }
  };
  const publish = async () => {
    // TODO: publish
    // actions.publishScenario();
    // await actions.saveBlocks(currentShifu?.bid || '');
    await actions.saveMdflow();
    alert.showAlert({
      confirmText: t('component.header.confirm'),
      cancelText: t('component.header.cancel'),
      title: t('component.header.confirmPublish'),
      description: t('component.header.confirmPublishDescription'),
      async onConfirm() {
        setPublishing(true);
        const result = await api.publishShifu({
          shifu_bid: currentShifu?.bid || '',
        });
        setPublishing(false);
        alert.showAlert({
          title: t('component.header.publishSuccess'),
          confirmText: t('component.header.goToView'),
          cancelText: t('component.header.close'),
          description: (
            <div className='flex flex-col space-y-2'>
              <span>{t('component.header.publishSuccessDescription')}</span>
              <a
                href={result}
                target='_blank'
                rel='noreferrer'
                className='text-blue-500 hover:underline'
              >
                {result}
              </a>
            </div>
          ),
          onConfirm() {
            window.open(result, '_blank');
          },
        });
      },
    });
  };
  return (
    <div className='flex items-center w-full h-16 px-2 py-2 bg-white border-b border-gray-200'>
      <div className='flex items-center space-x-4'>
        <Link
          href={'/main'}
          // className='flex items-center space-x-2 px-2 py-2 rounded-lg hover:bg-gray-100'
        >
          <Button
            variant='ghost'
            size='icon'
            className='h-9 w-9'
          >
            <Home className='h-5 w-5' />
          </Button>
        </Link>

        <div className='flex items-center'>
          {currentShifu?.avatar ? (
            <div className='bg-blue-100 flex items-center justify-center h-10 w-10 rounded-md p-1 mr-2 overflow-hidden'>
              <img
                src={currentShifu?.avatar}
                alt='Profile'
                className='rounded'
              />
            </div>
          ) : null}

          <div className='flex flex-col'>
            <div className='flex items-center'>
              <span className='font-medium text-sm'>{currentShifu?.name}</span>

              <span className='ml-1'>
                {isSaving && <Loading className='h-4 w-4 mr-1' />}
                {!error && !isSaving && lastSaveTime && (
                  <span className='flex flex-row items-center'>
                    <CircleCheck
                      height={18}
                      width={18}
                      className='mr-1  text-green-500'
                    />
                  </span>
                )}
                {error && (
                  <span className='flex flex-row items-center text-red-500'>
                    <CircleAlert
                      height={18}
                      width={18}
                      className='mr-1'
                    />{' '}
                    {error}
                  </span>
                )}
              </span>
            </div>

            {lastSaveTime && (
              <div
                key={lastSaveTime.getTime()}
                className='bg-gray-100 rounded px-2 py-1 text-xs text-gray-500 transform transition-all duration-300 ease-in-out translate-x-0 opacity-100 animate-slide-in'
              >
                {t('component.header.saved')} {lastSaveTime?.toLocaleString()}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className='flex-1'></div>

      <div className='flex flex-row items-center'>
        <ShifuSetting
          shifuId={currentShifu?.bid || ''}
          onSave={onShifuSave}
        />
        <Preivew />
        <Button
          size='sm'
          className='h-8 ml-1 bg-primary hover:bg-primary-lighter text-xs font-normal'
          onClick={publish}
          disabled
        >
          {publishing && <Loading className='h-4 w-4 mr-1' />}
          {!publishing && <TrendingUp />}
          {t('component.header.publish')}
        </Button>
      </div>
    </div>
  );
};

export default Header;
