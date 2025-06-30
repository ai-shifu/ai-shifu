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
    const { currentShifu, actions } = useShifu();

    const [autoSkipEmptyFields, setAutoSkipEmptyFields] = useState(false);

    const handleStartPreview = async () => {
        await actions.saveBlocks(currentShifu?.bid || '');
        // Handle the start preview action
        const result = await api.previewShifu({
            "shifu_bid": currentShifu?.bid || '',
            "skip": autoSkipEmptyFields,
            "variables": {}
        });
        setOpen(false);
        showAlert({
            title: t('preview.title'),
            confirmText: t('preview.view'),
            cancelText: t('preview.close'),
            description: (
                <div className="flex flex-col space-y-2">
                    {t('preview.link')}：<a href={result} target='_blank'>{result}</a>
                </div>
            ),
            onConfirm: () => {
                window.open(result, '_blank');
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

                <div >
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
