import Button from './button'
import Option from './option'

import SingleInput from './input'
import Goto from './goto'
import TextInput from './textinput'

import { useScenario } from '@/store';


const BlockMap = {
    button: Button,
    option: Option,
    goto: Goto,
    phone: SingleInput,
    code: SingleInput,
    textinput: TextInput,
}

export const RenderBlockContent = ({ id, type, properties }) => {
    const { actions } = useScenario();
    const onPropertiesChange = (properties) => {
        console.log(id, properties)
        actions.setBlockUIPropertiesById(id, properties)
    }
    const Ele = BlockMap[type]
    if (!Ele) {
        // console.log('type', type)
        return null
    }
    return (
        <Ele
            properties={properties}
            onChange={onPropertiesChange}
        />
    )
}

export default RenderBlockContent

export const UITypes = [
    {
        type: 'button',
        name: '按钮',
        properties: {
            "button_name": "继续",
            "button_key": "继续"
        }
    },
    {
        type: 'option',
        name: '按钮组',
        properties: {
            "option_name": "请输入",
            "option_key": "请输入",
            "profile_key": "Usage_level",
            "buttons": [
                {
                    "properties": {
                        "button_name": "全部",
                        "button_key": "全部"
                    },
                    "type": "button"
                },
                {
                    "properties": {
                        "button_name": "选项1",
                        "button_key": "选项1"
                    },
                    "type": "button"
                },
                {
                    "properties": {
                        "button_name": "选项2",
                        "button_key": "选项2"
                    },
                    "type": "button"
                }
            ]
        }
    },
    {
        type: 'goto',
        name: '跳转',
        properties: {
            "goto_settings": {
                "items": [
                    {
                        "value": "通义灵码",
                        "type": "outline",
                        "goto_id": "tblDUfFbHGnM4LQl"
                    },
                    {
                        "value": "GitHub_Copilot",
                        "type": "outline",
                        "goto_id": "tbl9gl38im3rd1HB"
                    }
                ],
                "profile_key": "ai_tools"
            },
            "button_name": "来吧",
            "button_key": "来吧"
        }
    },
    {
        type: 'textinput',
        name: '输入框',
        properties: {
            "prompt": {
                "properties": {
                    "prompt": "",
                    "profiles": [
                        "user_background"
                    ],
                    "model": "",
                    "temprature": "0.40",
                    "other_conf": ""
                },
                "type": "ai"
            },
            "input_name": "",
            "input_key": "",
            "input_placeholder": ""
        }
    },
    {
        type: 'phone',
        name: '手机号',
        properties: {
            "input_name": "",
            "input_key": "",
            "input_placeholder": "输入手机号"
        }
    },
    {
        type: 'code',
        name: '手机验证码',
        properties: {
            "input_name": "请输入4位数字验证码",
            "input_key": "请输入4位数字验证码",
            "input_placeholder": "请输入4位数字验证码"
        }
    },

]
