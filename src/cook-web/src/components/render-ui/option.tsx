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

interface ButtonProps {
    properties: {
        "option_name": string,
        "option_key": string,
        "profile_key": string,
        "buttons": {
            "properties": {
                "button_name": string,
                "button_key": string,
            },
            "type": string
        }[]
    }
    onChange: (properties: any) => void
    onChanged?: (changed: boolean) => void
}

const OptionPropsEqual = (prevProps: ButtonProps, nextProps: ButtonProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.option_name, nextProps.properties.option_name)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.option_key, nextProps.properties.option_key)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.profile_key, nextProps.properties.profile_key)) {
        return false
    }
    for (let i = 0; i < prevProps.properties.buttons.length; i++) {
        if (!_.isEqual(prevProps.properties.buttons[i], nextProps.properties.buttons[i])) {
            return false
        }
    }
    return true
}

export default memo(function Option(props: ButtonProps) {
    const { properties, onChanged } = props;
    const [changed, setChanged] = useState(false);
    const { t } = useTranslation();
    const { option_name, buttons } = properties;
    const [tempValue, setTempValue] = useState(option_name);
    const [tempButtons, setTempButtons] = useState(buttons.length === 0 ? [{
        "properties": {
            "button_name": t('option.button-name'),
            "button_key": t('option.button-key')
        },
        "type": "button"
    }] : buttons);
    const [showDeleteDialog, setShowDeleteDialog] = useState(false);
    const [deleteIndex, setDeleteIndex] = useState<number | null>(null);

    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!changed) {
            setChanged(true);
            onChanged?.(true);
        }
        setTempValue(e.target.value);
    }

    const onButtonValueChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        setTempButtons(tempButtons.map((button: any, i: number) => {
            if (i === index) {
                return {
                    ...button,
                    properties: {
                        ...button.properties,
                        button_key: e.target.value
                    }
                }
            }
            return button;
        }));
    }

    const onButtonTextChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        setTempButtons(tempButtons.map((button: any, i: number) => {
            if (i === index) {
                return {
                    ...button,
                    properties: {
                        ...button.properties,
                        button_name: e.target.value,
                    }
                }
            }
            return button;
        }));
    }

    const onAdd = (index: number) => {
        const newButton = {
            "properties": {
                "button_name": t('option.button-name'),
                "button_key": t('option.button-key')
            },
            "type": "button"
        }
        setTempButtons([
            ...tempButtons.slice(0, index + 1),
            newButton,
            ...tempButtons.slice(index + 1)
        ]);
    }

    const onDelete = (index: number) => {
        if (tempButtons.length === 1) {
            setDeleteIndex(index);
            setShowDeleteDialog(true);
        } else {
            setTempButtons(tempButtons.filter((_: any, i: number) => i !== index));
        }
    }

    const handleConfirmDelete = () => {
        if (deleteIndex !== null) {
            setTempButtons(tempButtons.filter((_: any, i: number) => i !== deleteIndex));
            setShowDeleteDialog(false);
            setDeleteIndex(null);
        }
    }

    const handleConfirm = () => {
        if (tempButtons.length === 0) {
            const defaultButton = {
                "properties": {
                    "button_name": t('option.button-name'),
                    "button_key": t('option.button-key')
                },
                "type": "button"
            };
            setTempButtons([defaultButton]);
        }

        const updatedProperties = {
            ...properties,
            option_name: tempValue,
            option_key: tempValue,
            buttons: tempButtons
        };
        props.onChange(updatedProperties);
    }

    return (
        <div className='flex flex-col space-y-1'>
            <div className='flex flex-row items-center'>
                <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                    {t('option.variable')}
                </span>
                <Input className='h-8 w-[400px]' placeholder={t('option.variable-placeholder')} value={tempValue} onChange={onValueChange}></Input>
            </div>
            <div className='flex flex-col space-y-2'>
                {
                    tempButtons.length === 0 ? (
                        <div className='flex flex-row items-center'>
                            <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                                {t('option.value')}
                            </span>
                            <Input className='w-40' placeholder={t('option.variable-placeholder')} value="全部" onChange={(e) => {
                                const newButton = {
                                    "properties": {
                                        "button_name": "全部",
                                        "button_key": e.target.value
                                    },
                                    "type": "button"
                                };
                                setTempButtons([newButton]);
                            }}></Input>
                            <span className='flex flex-row items-center whitespace-nowrap  w-[50px] ml-4'>
                                {t('option.title')}
                            </span>
                            <Input className='w-40 ml-4' placeholder={t('option.title-placeholder')} value="全部" onChange={(e) => {
                                const newButton = {
                                    "properties": {
                                        "button_name": e.target.value,
                                        "button_key": "全部"
                                    },
                                    "type": "button"
                                };
                                setTempButtons([newButton]);
                            }}></Input>
                            <Button className='h-8 w-8' variant="ghost" onClick={() => onAdd(-1)} >
                                <Plus />
                            </Button>
                        </div>
                    ) : (
                        tempButtons.map((button: any, index: number) => {
                            return (
                                <div key={index} className='flex flex-row items-center'>
                                    <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                                        {t('option.value')}
                                    </span>
                                    <Input value={button.properties.button_key} className='w-40' onChange={onButtonValueChange.bind(null, index)}></Input>
                                    <span className='flex flex-row items-center whitespace-nowrap  w-[50px] ml-4'>
                                        {t('option.title')}
                                    </span>
                                    <Input value={button.properties.button_name} className='w-40 ml-4' onChange={onButtonTextChange.bind(null, index)}></Input>
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
                <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                </span>
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
},OptionPropsEqual)
