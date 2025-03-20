"use client"
import { useScenario } from '@/store';
import AI from './ai'
import SolidContent from './solid-content'


const BlockMap = {
    ai: AI,
    systemprompt: AI,
    solidcontent: SolidContent,
}

export const RenderBlockContent = ({ id, type, properties }) => {
    const { actions } = useScenario();
    const onPropertiesChange = (properties) => {
        console.log(id, properties)
        actions.setBlockContentPropertiesById(id, properties)
    }
    const Ele = BlockMap[type]
    return (
        <Ele
            properties={properties}
            onChange={onPropertiesChange}
        />
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
