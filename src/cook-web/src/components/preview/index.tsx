import React, { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogTrigger
} from '@/components/ui/dialog';
import { Button } from '@/components/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { PlayIcon } from 'lucide-react';
import { useShifu } from '@/store';
import api from '@/api';
import { useAlert } from '@/components/ui/use-alert'
import { useTranslation } from 'react-i18next';

const PreviewSettingsModal = () => {
    const { t } = useTranslation();
    const { showAlert } = useAlert();
    const [open, setOpen] = useState(false);
    const { profileItemDefinations, currentShifu, actions } = useShifu();

    const [autoSkipEmptyFields, setAutoSkipEmptyFields] = useState(false);
    const [formValues, setFormValues] = useState({});

    const handleInputChange = (key, value) => {
        setFormValues(prev => ({ ...prev, [key]: value }));
    };
    const handleStartPreview = async () => {
        await actions.saveBlocks(currentShifu?.shifu_id || '');
        // Handle the start preview action
        const reuslt = await api.previewShifu({
            "shifu_id": currentShifu?.shifu_id || '',
            "skip": autoSkipEmptyFields,
            "variables": formValues
        });
        setOpen(false);
        showAlert({
            title: '预览',
            confirmText: '去查看',
            cancelText: '关闭',
            description: (
                <div className="flex flex-col space-y-2">
                    预览链接：<a href={reuslt} target='_blank'>{reuslt}</a>
                </div>
            ),
            onConfirm: () => {
                window.open(reuslt?.result, '_blank');
            }
        })
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-normal">
                    <PlayIcon />  {t('preview.preview')}
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-center text-xl font-medium">{t('preview.preview-settings')}</DialogTitle>
                </DialogHeader>

                <div className="py-4">
                    <div className='grid grid-cols-2 gap-4'>
                        <h3 className="mb-1 text-sm font-medium">{t('preview.variable-appear')}</h3>
                        <h3 className="mb-1 text-sm font-medium">{t('preview.input-variable-value')}</h3>
                        {
                            profileItemDefinations.map((field) => (
                                <>
                                    <Input
                                        value={field.profile_key}
                                    />
                                    <Input
                                        value={formValues[field.profile_key] || ''}
                                        onChange={(e) => handleInputChange
                                            (field.profile_key, e.target.value)}
                                    />
                                </>

                            ))
                        }
                    </div>

                    <div className="flex items-center justify-end space-x-2 mt-4">
                        <span className="text-sm">{t('preview.auto-skip')}</span>
                        <Switch
                            checked={autoSkipEmptyFields}
                            onCheckedChange={setAutoSkipEmptyFields}
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        className="w-full bg-purple-600 hover:bg-purple-700"
                        onClick={handleStartPreview}
                    >
                        {t('preview.start-preview')}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

export default PreviewSettingsModal;
