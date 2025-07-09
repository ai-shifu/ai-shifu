import React, { memo, useState } from 'react'
import { Input } from '../ui/input'
import { Plus, Trash } from 'lucide-react'
import { Button } from '../ui/button'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "../ui/alert-dialog"
import { useTranslation } from 'react-i18next';
import _ from 'lodash'
import { ProfileFormItem } from '@/components/profiles'
import { OptionsDTO, UIBlockDTO } from '@/types/shifu'
import i18n from '@/i18n'


const OptionPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
    const prevOptionsSettings = prevProps.data.properties as OptionsDTO
    const nextOptionsSettings = nextProps.data.properties as OptionsDTO
    if (!_.isEqual(prevProps.data, nextProps.data)) {
        return false
    }
    if (!_.isEqual(prevOptionsSettings.result_variable_bid, nextOptionsSettings.result_variable_bid)) {
        return false
    }
    for (let i = 0; i < prevOptionsSettings.options.length; i++) {
        if (!_.isEqual(prevOptionsSettings.options[i], nextOptionsSettings.options[i])) {
            return false
        }
    }
    return true
}

export default memo(function Option(props: UIBlockDTO) {
    const { data } = props;
    // const [changed, setChanged] = useState(false);
    const { t } = useTranslation();
    const optionsSettings = data.properties as OptionsDTO
    const [tempValue, setTempValue] = useState<string>(optionsSettings.result_variable_bid);
    const [tempOptions, setTempOptions] = useState(optionsSettings.options.length === 0 ? [{
        "value": t('option.button-key'),
        "label": {
            "lang": {
                "zh-CN": t('option.button-name'),
                "en-US": t('option.button-name')
            }
        }
    }] : optionsSettings.options);
    const [showDeleteDialog, setShowDeleteDialog] = useState(false);
    const [deleteIndex, setDeleteIndex] = useState<number | null>(null);

    const onButtonValueChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        setTempOptions(tempOptions.map((option: any, i: number) => {
            if (i === index) {
                return {
                    ...option,
                    value: e.target.value
                }
            }
            return option;
        }));
    }

    const onButtonTextChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        setTempOptions(tempOptions.map((option: any, i: number) => {
            if (i === index) {
                return {
                    ...option,
                    label: {
                        ...option.label,
                        lang: {
                            ...option.label.lang,
                            "zh-CN": e.target.value,
                            "en-US": e.target.value
                        }
                    }
                }
            }
            return option;
        }));
    }

    const onAdd = (index: number) => {
        const newOption = {
            "label": {
                "lang": {
                    "zh-CN": t('option.button-name'),
                    "en-US": t('option.button-name')
                },

            },
            "value": t('option.button-key')
        }
        setTempOptions([
            ...tempOptions.slice(0, index + 1),
            newOption,
            ...tempOptions.slice(index + 1)
        ]);
    }

    const onDelete = (index: number) => {
        if (tempOptions.length === 1) {
            setDeleteIndex(index);
            setShowDeleteDialog(true);
        } else {
            setTempOptions(tempOptions.filter((_: any, i: number) => i !== index));
        }
    }

    const handleConfirmDelete = () => {
        if (deleteIndex !== null) {
            setTempOptions(tempOptions.filter((_: any, i: number) => i !== deleteIndex));
            setShowDeleteDialog(false);
            setDeleteIndex(null);
        }
    }

    const handleConfirm = () => {
        if (tempOptions.length === 0) {
            const defaultButton = {
                "value": t('option.button-key'),
                "label": {
                    "lang": {
                        'zh-CN': t('option.button-name'),
                        'en-US': t('option.button-name')
                    },
                }
            };
            setTempOptions([defaultButton]);
        }

        const updatedProperties = {
            ...data,
            properties: {
                ...data.properties,
                options: tempOptions,
                result_variable_bid: tempValue
            },
            variable_bids: [tempValue]
        }
        props.onPropertiesChange(updatedProperties);
    }

    const handleProfileChange = (value: string[]) => {
        setTempValue(value?.[0])
    }

    return (
        <div className='flex flex-col space-y-1 space-x-1'>
            <div className='flex flex-row items-center'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('option.variable')}
                </label>
                <ProfileFormItem value={[tempValue || '']} onChange={handleProfileChange} />
            </div>
            <div className='flex flex-col space-y-2'>
                {
                    tempOptions.length === 0 ? (
                        <div className='flex flex-row items-center'>
                            <span className='flex flex-row items-center whitespace-nowrap  w-[70px] shrink-0'>
                                {t('option.value')}
                            </span>
                            <Input className='w-40' placeholder={t('option.variable-placeholder')} value="全部" onChange={(e) => {
                                const newOption = {
                                    "label": {
                                        "lang": {
                                            "zh-CN": "全部",
                                            "en-US": "全部"
                                        },
                                    },
                                    "value": e.target.value
                                };
                                setTempOptions([newOption]);
                            }}></Input>
                            <label htmlFor="" className='whitespace-nowrap w-[50px] shrink-0 ml-4'>
                                {t('option.title')}
                            </label>
                            <Input className='w-40 ml-4' placeholder={t('option.title-placeholder')} value="全部" onChange={(e) => {
                                const newOption = {
                                    "label": {
                                        "lang": {
                                            "zh-CN": e.target.value,
                                            "en-US": e.target.value
                                        },
                                    },
                                    "value": "全部"
                                };
                                setTempOptions([newOption]);
                            }}></Input>
                            <Button className='h-8 w-8' variant="ghost" onClick={() => onAdd(-1)} >
                                <Plus />
                            </Button>
                        </div>
                    ) : (
                        tempOptions.map((option: any, index: number) => {
                            return (
                                <div key={index} className='flex flex-row items-center'>
                                    <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                                        {t('option.value')}
                                    </label>
                                    <Input value={option.value} className='w-40' onChange={onButtonValueChange.bind(null, index)}></Input>
                                    <label htmlFor="" className='whitespace-nowrap w-[50px] shrink-0 ml-4'>
                                        {t('option.title')}
                                    </label>
                                    <Input value={option.label.lang[i18n.language]} className='w-40 ml-4' onChange={onButtonTextChange.bind(null, index)}></Input>
                                    <Button className='h-8 w-8' variant="ghost" onClick={onAdd.bind(null, index)} >
                                        <Plus />
                                    </Button>
                                    <Button className='h-8 w-8' variant="ghost" onClick={onDelete.bind(null, index)} >
                                        <Trash />
                                    </Button>
                                </div>
                            )
                        })
                    )
                }
            </div>
            <div className='flex flex-row items-center'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                </label>
                <Button
                    className='h-8 w-20'
                    onClick={handleConfirm}
                >
                    {t('option.complete')}
                </Button>
            </div>
            <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('option.confirm-delete')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('option.confirm-delete-description')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t('option.cancel')}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmDelete}>{t('option.confirm')}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}, OptionPropsEqual)
