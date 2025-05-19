"use client"
import { useShifu } from '@/store';
import AI from './ai'
import SolidContent from './solid-content'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Check, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../ui/alert-dialog';
import { useTranslation } from 'react-i18next';

const BlockMap = {
    ai: AI,
    solidcontent: SolidContent,
}

export const RenderBlockContent = ({ id, type, properties }) => {
    const { t } = useTranslation();
    const { actions, blocks, blockContentTypes, blockContentState, currentNode, blockUITypes, blockContentProperties, blockUIProperties, currentShifu } = useShifu();
    const [error, setError] = useState('')
    const [showDeleteDialog, setShowDeleteDialog] = useState(false)
    const ContentTypes = useContentTypes()

    const onPropertiesChange = async (properties) => {
        await actions.setBlockContentPropertiesById(id, properties)
        const p = {
            ...blockContentProperties,
            [id]: {
                ...blockContentProperties[id],
                ...properties
            }
        }
        setError('')
        if (type == 'ai' && properties.prompt == '') {
            setError(t('render-block.ai-content-empty'))
            return;
        } else if (type == 'solidcontent' && properties.content == '') {
            setError(t('render-block.solid-content-empty'))
            return;
        }
        if (currentNode) {
            actions.autoSaveBlocks(currentNode.id, blocks, blockContentTypes, p, blockUITypes, blockUIProperties, currentShifu?.shifu_id || '')
        }
    }

    const onContentTypeChange = (id: string, type: string) => {
        const opt = ContentTypes.find(p => p.type === type);
        actions.setBlockContentTypesById(id, type)
        actions.setBlockContentPropertiesById(id, opt?.properties || {} as any, true)
    }
    const setIsEdit = (isEdit: boolean) => {
        actions.setBlockContentStateById(id, isEdit ? 'edit' : 'preview')
    }
    const onSave = async () => {
        setError('')
        // check if the block is empty
        const block = blocks.find((item) => item.properties.block_id == id);
        if (type == 'ai' && block && properties.prompt == '') {
            setError(t('render-block.ai-content-empty'))
            return;
        } else if (type == 'solidcontent' && block && properties.content == '') {
            setError(t('render-block.solid-content-empty'))
            return;
        }
        setIsEdit(false)
        await actions.saveBlocks(currentShifu?.shifu_id || '');
    }
    const onRemove = async () => {
        setShowDeleteDialog(true)
    }

    const handleConfirmDelete = async () => {
        if (!currentNode?.id) return;
        await actions.removeBlock(id, currentShifu?.shifu_id || '');
        setShowDeleteDialog(false)
    }

    const isEdit = blockContentState[id] == 'edit';
    const Ele = BlockMap[type]
    return (
        <div className='bg-[#F5F5F4] rounded-md'>
            {
                isEdit && (
                    <div className='rounded-t-md p-2 flex flex-row items-center py-1 justify-between'>
                        <Select
                            value={blockContentTypes[id]}
                            onValueChange={onContentTypeChange.bind(null, id)}
                        >
                            <SelectTrigger className="h-8 w-[120px]">
                                <SelectValue placeholder={t('render-block.select-content-type')} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectGroup>
                                    {
                                        ContentTypes.map((item) => {
                                            return (
                                                <SelectItem key={item.type} value={item.type}>{item.name}</SelectItem>
                                            )
                                        })
                                    }
                                </SelectGroup>
                            </SelectContent>
                        </Select>
                        <div className='flex flex-row items-center'>
                            <div className='flex flex-row items-center px-2' onClick={onRemove}>
                                <Trash2 className='h-5 w-5 cursor-pointer' />
                            </div>
                            <div className='h-4 border-r border-[#D8D8D8] mx-1'></div>
                            <div className='flex flex-row items-center cursor-pointer px-2 ' onClick={onSave} >
                                <Check className='h-5 w-5 text-primary mr-2 shrink-0' />{t('render-block.complete')}
                            </div>
                        </div>
                    </div>
                )
            }

            <div onDoubleClick={() => {
                setIsEdit(true)
            }}>
                <Ele
                    isEdit={isEdit}
                    properties={properties}
                    onChange={onPropertiesChange}
                />
            </div>
            {
                error && (
                    <div className='text-red-500 text-sm px-2 pb-2'>{error}</div>
                )
            }

            <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('render-block.confirm-delete')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('render-block.confirm-delete-description')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t('render-block.cancel')}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmDelete}>{t('render-block.confirm')}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}

export default RenderBlockContent;

export const useContentTypes = () =>
    {
        const { t } = useTranslation();
        return [
            {
                type: 'ai',
                name: t('render-block.ai-content'),
                properties: {
            "prompt": "",
            "profiles": [],
            "model": "",
            "temprature": "0.40",
            "other_conf": ""
            }
        },
        {
            type: 'solidcontent',
            name: t('render-block.solid-content'),
            properties: {
                "content": "",
                "profiles": [],
            }
            }
        ]
}
