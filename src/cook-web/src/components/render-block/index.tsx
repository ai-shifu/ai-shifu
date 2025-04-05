"use client"
import { useScenario } from '@/store';
import AI from './ai'
import SolidContent from './solid-content'


import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Trash, Check } from 'lucide-react';
import Button from '../button';


const BlockMap = {
    ai: AI,
    systemprompt: AI,
    solidcontent: SolidContent,
}

export const RenderBlockContent = ({ id, type, properties }) => {
    const { actions, blocks, blockContentTypes, blockContentState, currentOutline, blockUITypes, blockContentProperties, blockUIProperties } = useScenario();
    const onPropertiesChange = async (properties) => {
        console.log(id, properties)
        await actions.setBlockContentPropertiesById(id, properties)
        const p = {
            ...blockContentProperties,
            [id]: {
                ...blockContentProperties[id],
                ...properties
            }
        }
        actions.autoSaveBlocks(currentOutline, blocks, blockContentTypes, p, blockUITypes, blockUIProperties)
    }

    const onContentTypeChange = (id: string, type: string) => {
        const opt = ContentTypes.find(p => p.type === type);
        actions.setBlockContentTypesById(id, type)
        actions.setBlockContentPropertiesById(id, opt?.properties || {})
    }
    const setIsEdit = (isEdit: boolean) => {
        actions.setBlockContentStateById(id, isEdit ? 'edit' : 'preview')
    }
    const onSave = async () => {
        setIsEdit(false)
        await actions.saveBlocks();
    }
    const onRemove = async () => {
        // await actions.removeBlockById(id)
        actions.removeBlock(id);
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
                                <SelectValue placeholder="请选择" />
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
                        <div className='flex flex-row'>
                            <div className='flex flex-row items-center w-6 ' onClick={onRemove}>
                                <Trash className='h-5 w-5 cursor-pointer' />
                            </div>
                            <Button variant='ghost' className=' cursor-pointer' onClick={onSave} >
                                <Check />完成
                            </Button>
                        </div>
                    </div>

                )
            }

            <div onDoubleClick={() => setIsEdit(true)}>
                <Ele
                    isEdit={isEdit}
                    properties={properties}
                    onChange={onPropertiesChange}
                />
            </div>

        </div>

    )
}

export default RenderBlockContent;

export const ContentTypes = [
    {
        type: 'ai',
        name: 'AI块',
        properties: {
            "prompt": "请输入",
            "profiles": [
                "nickname",
                "user_background"
            ],
            "model": "",
            "temprature": "0.40",
            "other_conf": ""
        }
    },
    {
        type: 'systemprompt',
        name: '系统提示词',
        properties: {
            "prompt": "请输入",
            "profiles": [
                "nickname",
                "user_background"
            ],
            "model": "",
            "temprature": "0.40",
            "other_conf": ""
        }
    },
    {
        type: 'solidcontent',
        name: '固定内容',
        properties: {
            "content": "请输入",
            "profiles": [
                "nickname",
                "user_background"
            ],
        }
    }
]
