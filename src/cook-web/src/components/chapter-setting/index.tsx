import React, { useEffect, useState, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Editor } from '@/components/cm-editor';
import api from '@/api';
import Loading from '../loading';

import { useTranslation } from 'react-i18next';
import { useShifu } from '@/store';

const ChapterSettingsDialog = ({ outlineBid, open, onOpenChange }: { outlineBid: string; open: boolean; onOpenChange?: (open: boolean) => void; }) => {
    const { currentShifu } = useShifu();
    const { t } = useTranslation();
    const [chapterType, setChapterType] = useState("normal");
    const [systemPrompt, setSystemPrompt] = useState("");
    const [hideChapter, setHideChapter] = useState(true);
    const [loading, setLoading] = useState(false);

    const init = useCallback(async () => {
        setLoading(true);
        const result = await api.getOutlineInfo({
            outline_bid: outlineBid,
            shifu_bid: currentShifu?.bid
        })
        setChapterType(result.type);
        setSystemPrompt(result.system_prompt);
        setHideChapter(result.is_hidden);
        setLoading(false);
    }, [outlineBid, currentShifu?.bid]);

    const onConfirm = async () => {
        await api.modifyOutline({
            "outline_bid": outlineBid,
            "is_hidden": hideChapter,
            "system_prompt": systemPrompt,
            "type": chapterType,
            "shifu_bid": currentShifu?.bid
        })
        onOpenChange?.(false);
    }

    useEffect(() => {
        if (!open) {
            setChapterType("formal");
            setSystemPrompt("");
            setHideChapter(true);
        } else {
            init();
        }
        onOpenChange?.(open);
    }, [open, outlineBid, onOpenChange, init])

    return (
        <Dialog
            open={open}
            onOpenChange={(newOpen) => {
                if (document.activeElement?.tagName === 'INPUT' ||
                    document.activeElement?.tagName === 'TEXTAREA' ||
                    document.activeElement?.getAttribute('role') === 'radio' ||
                    document.activeElement?.getAttribute('role') === 'checkbox') {
                    return;
                }
                onOpenChange?.(newOpen);
            }}
        >
            <DialogContent
                className="sm:max-w-lg lg:max-w-[70vw] bg-gray-100"
                onPointerDown={(e) => {
                    e.stopPropagation();
                }}
            >
                <DialogHeader>
                    <DialogTitle className="text-lg font-medium">{t('chapter-setting.title')}</DialogTitle>
                </DialogHeader>
                {
                    loading && (
                        <div className='flex justify-center items-center h-24'>
                            <Loading />
                        </div>
                    )
                }
                {
                    !loading && (
                        <div className="space-y-6 py-4">
                            <div className="flex items-center space-x-4">
                                <div className="w-24 text-sm">{t('chapter-setting.chapter-type')}</div>
                                <RadioGroup
                                    value={chapterType}
                                    onValueChange={setChapterType}
                                    className="flex space-x-6"
                                >
                                    <div className="flex items-center space-x-2">
                                        <RadioGroupItem value="normal" id="formal" />
                                        <Label htmlFor="formal">{t('chapter-setting.formal-chapter')}</Label>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                        <RadioGroupItem value="trial" id="trial" />
                                        <Label htmlFor="trial">{t('chapter-setting.trial-chapter')}</Label>
                                    </div>
                                </RadioGroup>
                            </div>

                            <div className="flex space-x-4">
                                <div className="w-24 text-sm mt-2">{t('chapter-setting.system-prompt')}</div>
                                <div className="w-full rounded-md border bg-background px-1 py-1">
                                    <div style={{ minHeight: '72px', maxHeight: '480px', overflowY: 'auto' }}>
                                        <Editor
                                            content={systemPrompt}
                                            onChange={(value) => setSystemPrompt(value)}
                                            isEdit={true}
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center space-x-4">
                                <div className="w-24 text-sm">{t('chapter-setting.is-hidden')}</div>
                                <div className="flex items-center space-x-2">
                                    <Checkbox
                                        id="hideChapter"
                                        checked={hideChapter}
                                        onCheckedChange={setHideChapter as any}
                                    />
                                    <Label htmlFor="hideChapter">{t('chapter-setting.hide-chapter')}</Label>
                                </div>
                            </div>
                        </div>
                    )
                }
                <div className="flex justify-end space-x-2 pt-4">
                    <Button variant="outline" onClick={()=> onOpenChange?.(false)}>
                        {t('common.cancel')}
                    </Button>
                    <Button disabled={loading} onClick={onConfirm}>
                        {t('common.confirm')}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default ChapterSettingsDialog;
