"use client"
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';
import { useScenario } from '@/store';
import Loading from '../loading';
import { useAlert } from '@/components/ui/use-alert';
import api from '@/api'
import { ChevronLeft, CircleAlert, CircleCheck, TrendingUp } from 'lucide-react';
import Preivew from '@/components/preview';
import CourseSetting from '@/components/course-setting';
import { useTranslation } from 'react-i18next';
const Header = () => {
    const { t } = useTranslation();
    const alert = useAlert();
    const router = useRouter();
    const [publishing, setPublishing] = useState(false);
    const { isSaving, lastSaveTime, currentScenario, error, actions } = useScenario();
    const onCourseSave = async () => {
        if (currentScenario) {
            await actions.loadScenario(currentScenario.id);
        }
    }
    const publish = async () => {
        // TODO: publish
        // actions.publishScenario();
        await actions.saveBlocks(currentScenario?.id || '');
        alert.showAlert({
            confirmText: t('header.confirm'),
            cancelText: t('header.cancel'),
            title: t('header.confirm-publish'),
            description: t('header.confirm-publish-description'),
            async onConfirm() {
                setPublishing(true)
                const reuslt = await api.publishScenario({
                    scenario_id: currentScenario?.id || ''
                });
                setPublishing(false)
                alert.showAlert({
                    title: t('header.publish-success'),
                    confirmText: t('header.go-to-view'),
                    cancelText: t('header.close'),
                    description: (
                        <div className="flex flex-col space-y-2">
                            <span>{t('header.publish-success-description')}</span>
                            <a href={reuslt} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">
                                {reuslt}
                            </a>
                        </div >
                    ),
                    onConfirm() {
                        window.open(reuslt, '_blank');
                    }
                })
            },
        })
    }
    return (
        <div className="flex items-center w-full h-14 px-2 py-2 bg-white border-b border-gray-200">
            <div className="flex items-center space-x-4">
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => router.back()}>
                    <ChevronLeft className="h-5 w-5" />
                </Button>

                <div className="flex items-center">
                    {
                        currentScenario?.image ? (
                            <div className="bg-blue-100 flex items-center justify-center h-10 w-10 rounded-md p-1 mr-2 overflow-hidden">
                                <img
                                    src={currentScenario?.image}
                                    alt="Profile"
                                    className="rounded"
                                />
                            </div>
                        ) : null
                    }

                    <div className='flex flex-col'>
                        <div className="flex items-center">
                            <span className="font-medium text-sm">
                                {currentScenario?.name}
                            </span>

                            <span className='ml-1'>
                                {
                                    isSaving && (
                                        <Loading className='h-4 w-4 mr-1' />
                                    )
                                }
                                {
                                    !error && (!isSaving && lastSaveTime) && (
                                        <span className='flex flex-row items-center'>
                                            <CircleCheck height={18} width={18} className='mr-1  text-green-500' />
                                        </span>
                                    )
                                }
                                {
                                    error && (
                                        <span className='flex flex-row items-center text-red-500'>
                                            <CircleAlert height={18} width={18} className='mr-1' />  {error}
                                        </span>
                                    )
                                }
                            </span>
                        </div>

                        {
                            lastSaveTime && (
                                <div key={lastSaveTime.getTime()} className='bg-gray-100 rounded px-2 py-1 text-xs text-gray-500 transform transition-all duration-300 ease-in-out translate-x-0 opacity-100 animate-slide-in'>
                                    {t('header.saved')} {lastSaveTime?.toLocaleString()}
                                </div>
                            )
                        }

                    </div>

                </div>
            </div>
            <div className='flex-1'>

            </div>

            <div className='flex flex-row items-center'>
                <CourseSetting scenarioId={currentScenario?.id || ""} onSave={onCourseSave} />
                <Preivew />
                <Button size="sm" className="h-8 ml-1 bg-purple-600 hover:bg-purple-700 text-xs font-normal"
                    onClick={publish}
                >
                    {
                        publishing && (
                            <Loading className='h-4 w-4 mr-1' />
                        )
                    }
                    {
                        !publishing && (
                            <TrendingUp />
                        )
                    }
                    {t('header.publish')}
                </Button>
            </div>
        </div>
    );
};

export default Header;
