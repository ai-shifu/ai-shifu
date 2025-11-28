'use client';
import React, { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { useShifu } from '@/store';
import Loading from '../loading';
import { useAlert } from '@/components/ui/UseAlert';
import api from '@/api';
import {
  ChevronLeft,
  CircleAlert,
  CircleCheck,
  TrendingUp,
} from 'lucide-react';
import Preivew from '@/components/preview';
import ShifuSetting from '@/components/shifu-setting';
import { useTranslation } from 'react-i18next';
import s from './header.module.scss';

const Header = () => {
  const { t } = useTranslation();
  const alert = useAlert();
  const router = useRouter();
  const [publishing, setPublishing] = useState(false);
  const { isSaving, lastSaveTime, currentShifu, error, actions } = useShifu();
  const onShifuSave = async () => {
    if (currentShifu) {
      await actions.loadShifu(currentShifu.bid, { silent: true });
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
    <div className='flex items-center w-full h-16 px-4 py-[11px] bg-white border-b border-gray-200'>
      <div className='flex items-center space-x-4'>
        <Link href={'/admin'}>
          <ChevronLeft size={24} />
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
              <span className='text-black text-base not-italic font-semibold leading-7'>
                {currentShifu?.name}
              </span>
              {currentShifu?.readonly && (
                <span className={s.readonly}>
                  {t('component.header.readonly')}
                </span>
              )}
            </div>

            <div className='flex items-center'>
              {isSaving && <Loading className='h-4 w-4 mr-1' />}
              {!error && !isSaving && lastSaveTime && (
                <span className='flex flex-row items-center'>
                  <CircleCheck
                    size={16}
                    className='mr-2  text-green-500'
                  />
                </span>
              )}
              {error && (
                <span className='flex flex-row items-center text-red-500'>
                  <CircleAlert
                    size={16}
                    className='mr-2'
                  />{' '}
                  {error}
                </span>
              )}
              {lastSaveTime && (
                <div
                  key={lastSaveTime.getTime()}
                  style={{ color: 'rgba(0, 0, 0, 0.45)' }}
                  className='text-sm not-italic font-normal bg-white leading-5 tracking-normal transform transition-all duration-300 ease-in-out translate-x-0 animate-slide-in'
                >
                  {t('component.header.saved')} {lastSaveTime?.toLocaleString()}
                </div>
              )}
            </div>
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
        <div className='flex items-center justify-center h-9 rounded-lg cursor-pointer shifu-setting-icon-container ml-2'>
          <Button
            size='sm'
            className=''
            onClick={publish}
          >
            {publishing && <Loading className='h-4 w-4 mr-1' />}
            <span className='title text-white'>
              {t('component.header.publish')}
            </span>
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Header;
