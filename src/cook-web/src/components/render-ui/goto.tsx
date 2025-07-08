import React, { useEffect, useState } from 'react'

import OutlineSelector from '@/components/outline-selector'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { useShifu } from '@/store'
import { Outline, GotoDTO, ProfileItemDefination, UIBlockDTO } from '@/types/shifu'
import api from '@/api'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'


const GotoPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
    const prevGotoSettings = prevProps.data.properties as GotoDTO
    const nextGotoSettings = nextProps.data.properties as GotoDTO
    if (!_.isEqual(prevProps.data, nextProps.data)) {
        return false
    }

    if (!_.isEqual(prevGotoSettings.conditions, nextGotoSettings.conditions)) {
        return false
    }
    for (let i = 0; i < prevGotoSettings.conditions.length; i++) {
        if (!_.isEqual(prevGotoSettings.conditions[i].value, nextGotoSettings.conditions[i].value)
            || !_.isEqual(prevGotoSettings.conditions[i].destination_bid, nextGotoSettings.conditions[i].destination_bid)
            || !_.isEqual(prevGotoSettings.conditions[i].destination_type, nextGotoSettings.conditions[i].destination_type)
        ) {
            return false
        }
    }

    return true
}

export default memo(function Goto(props: UIBlockDTO) {
    const { data, onChanged } = props
    const [changed, setChanged] = useState(false);
    const { t } = useTranslation();
    const { chapters, currentShifu } = useShifu();

    const [profileItemDefinations, setProfileItemDefinations] = useState<ProfileItemDefination[]>([]);
    const [variableBid, setVariableBid] = useState<string>(data.variable_bids?.[0] || "");
    const [selectedProfile, setSelectedProfile] = useState<ProfileItemDefination | null>(null);
    const gotoSettings = data.properties as GotoDTO
    const [tempGotoSettings, setTempGotoSettings] = useState(gotoSettings);


    const onNodeSelect = (index: number, node: Outline) => {
        setTempGotoSettings({
            ...tempGotoSettings,
            conditions: tempGotoSettings.conditions.map((item, i) => {
                if (i === index) {
                    return {
                        ...item,
                        destination_bid: node.id
                    }
                }
                return item
            })
        });
    }

    const handleConfirm = () => {
        props.onPropertiesChange({
            ...data,
            properties: tempGotoSettings,
            variable_bids: [variableBid]
        });
        onChanged?.(true);
    }

    const loadProfileItemDefinations = async (preserveSelection: boolean = false) => {
        const list = await api.getProfileItemDefinitions({
            parent_id: currentShifu?.bid,
            type: "option"
        })
        setProfileItemDefinations(list)
        if (!preserveSelection && list.length > 0) {
            const initialSelected = list.find((item) => item.profile_id === variableBid);
            if (initialSelected) {
                setSelectedProfile(initialSelected);
                await loadProfileItem(initialSelected.profile_id);
            }
        }
    }

    const loadProfileItem = async (id: string) => {
        setVariableBid(id);
        const list = await api.getProfileItemOptionList({
            parent_id: id
        })
        const conditions = list.map((item) => {
            const existingCondition = tempGotoSettings.conditions.find((condition) => condition.value === item.value);
            if (existingCondition) {
                return existingCondition;
            }
            return {
                value: item.value,
                destination_bid: "",
                destination_type: "outline"
            }
        })
        setTempGotoSettings({
            ...tempGotoSettings,
            conditions: conditions
        });
    }

    useEffect(() => {
        loadProfileItemDefinations();
    }, [])

    const handleValueChange = async (value: string) => {
        setVariableBid(value);
        if (!changed) {
            setChanged(true);
            onChanged?.(true);
        }
        const selectedItem = profileItemDefinations.find((item) => item.profile_id === value);
        if (selectedItem) {
            setSelectedProfile(selectedItem);
            await loadProfileItem(value);
        }
    }

    return (
        <div className='flex flex-col space-y-1'>
            <div className='flex flex-row items-center space-x-1'>
                <div className='flex flex-row whitespace-nowrap w-[70px] shrink-0'>
                    {t('goto.select-variable')}
                </div>
                <Select
                    value={selectedProfile?.profile_key || ""}
                    onValueChange={handleValueChange}
                    onOpenChange={(open) => {
                        if (open) {
                            loadProfileItemDefinations(true);
                        }
                    }}
                >
                    <SelectTrigger className="h-8 w-[170px]">
                        <SelectValue>
                            {selectedProfile?.profile_key || t('goto.select-variable')}
                        </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                        {
                            profileItemDefinations?.map((item) => {
                                return <SelectItem key={item.profile_key} value={item.profile_id} >{item.profile_key}</SelectItem>
                            })
                        }
                    </SelectContent>
                </Select>
            </div>
            <div className='flex flex-row items-start py-2'>
                <div className='flex flex-row whitespace-nowrap w-[70px] shrink-0'>
                    {t('goto.goto-settings')}
                </div>
                <div className='flex flex-col space-y-1 '>
                    {
                        tempGotoSettings.conditions.map((item, index) => {
                            return (
                                <div className='flex flex-row items-center space-x-2' key={`${item.destination_bid}-${index}`}>
                                    <span className='w-40'>{item.value}</span>
                                    <span className='px-2'>{t('goto.goto-settings-jump-to')}</span>
                                    <span>
                                        <OutlineSelector value={item.destination_bid} chapters={chapters} onSelect={onNodeSelect.bind(null, index)} />
                                    </span>
                                </div>
                            )
                        })
                    }
                </div>
            </div>
            <div className='flex flex-row items-center'>
                <span className='flex flex-row items-center whitespace-nowrap w-[70px] shrink-0'>
                </span>
                <Button
                    className='h-8 w-20'
                    onClick={handleConfirm}
                >
                    {t('goto.complete')}
                </Button>
            </div>
        </div>
    )
}, GotoPropsEqual)
