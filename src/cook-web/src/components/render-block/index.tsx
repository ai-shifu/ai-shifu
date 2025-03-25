"use client"
import { useScenario } from '@/store';
import AI from './ai'
import SolidContent from './solid-content'


import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Trash, Check } from 'lucide-react';
import Button from '../button';
import { useState } from 'react';



const BlockMap = {
    ai: AI,
    systemprompt: AI,
    solidcontent: SolidContent,
}

export const RenderBlockContent = ({ id, type, properties }) => {

    const [isEdit, setIsEdit] = useState(false)
    const { actions, blockContentTypes } = useScenario();
    const onPropertiesChange = (properties) => {
        console.log(id, properties)
        actions.setBlockContentPropertiesById(id, properties)
    }

    const onContentTypeChange = (id: string, type: string) => {
        const opt = ContentTypes.find(p => p.type === type);
        actions.setBlockContentTypesById(id, type)
        actions.setBlockContentPropertiesById(id, opt?.properties || {})
    }

    const Ele = BlockMap[type]
    return (
        <div>
            {
                isEdit && (
                    <div className='flex flex-row items-center py-1 justify-between'>
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
                            <div className='flex flex-row items-center w-6 '>
                                <Trash className='h-5 w-5 cursor-pointer' />
                            </div>
                            <Button variant='ghost' className=' cursor-pointer' onClick={() => setIsEdit(false)} >
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
