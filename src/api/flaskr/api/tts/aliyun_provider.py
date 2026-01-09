"""
Aliyun TTS Provider.

This module provides TTS synthesis using Aliyun's Intelligent Speech Interaction
RESTful API.

API Reference:
- Endpoint: https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts
- Documentation: https://help.aliyun.com/zh/isi/developer-reference/restful-api-3
"""

import logging
import requests
from typing import Optional, List

from flaskr.common.config import get_config
from flaskr.api.tts.base import (
    BaseTTSProvider,
    TTSResult,
    VoiceSettings,
    AudioSettings,
    ProviderConfig,
    ParamRange,
)


logger = logging.getLogger(__name__)

# Aliyun TTS API endpoints by region
ALIYUN_TTS_ENDPOINTS = {
    "shanghai": "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts",
    "beijing": "https://nls-gateway-cn-beijing.aliyuncs.com/stream/v1/tts",
    "shenzhen": "https://nls-gateway-cn-shenzhen.aliyuncs.com/stream/v1/tts",
}

# Aliyun audio format mapping
ALIYUN_AUDIO_FORMATS = {
    "mp3": "mp3",
    "wav": "wav",
    "pcm": "pcm",
}

# Aliyun voice IDs - Complete list
# Reference: https://help.aliyun.com/zh/isi/developer-reference/overview-of-speech-synthesis
ALIYUN_VOICES = [
    # 通用场景 - 标准音色
    {
        "id": "xiaoyun",
        "name": "小云",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "标准女声",
    },
    {
        "id": "xiaogang",
        "name": "小刚",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "标准男声",
    },
    {
        "id": "ruoxi",
        "name": "若兮",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "siqi",
        "name": "思琪",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "sijia",
        "name": "思佳",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "标准女声",
    },
    {
        "id": "sicheng",
        "name": "思诚",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "标准男声",
    },
    {
        "id": "aiqi",
        "name": "艾琪",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "aijia",
        "name": "艾佳",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "标准女声",
    },
    {
        "id": "aicheng",
        "name": "艾诚",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "标准男声",
    },
    {
        "id": "aida",
        "name": "艾达",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "标准男声",
    },
    {
        "id": "ninger",
        "name": "宁儿",
        "type": "standard",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
    {
        "id": "ruilin",
        "name": "瑞琳",
        "type": "standard",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
    # 客服场景
    {
        "id": "siyue",
        "name": "思悦",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "aiya",
        "name": "艾雅",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "严厉女声",
    },
    {
        "id": "aimei",
        "name": "艾美",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "甜美女声",
    },
    {
        "id": "aiyu",
        "name": "艾雨",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "自然女声",
    },
    {
        "id": "aiyue",
        "name": "艾悦",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "aijing",
        "name": "艾婧",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "严厉女声",
    },
    {
        "id": "xiaomei",
        "name": "小美",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh-en",
        "desc": "甜美女声",
    },
    {
        "id": "aina",
        "name": "艾娜",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh",
        "desc": "浙普女声",
    },
    {
        "id": "yina",
        "name": "伊娜",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh",
        "desc": "浙普女声",
    },
    {
        "id": "sijing",
        "name": "思婧",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh",
        "desc": "严厉女声",
    },
    {
        "id": "aishuo",
        "name": "艾硕",
        "type": "customer_service",
        "gender": "male",
        "lang": "zh-en",
        "desc": "自然男声",
    },
    {
        "id": "zhiya",
        "name": "知雅",
        "type": "customer_service",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
    # 童声场景
    {
        "id": "sitong",
        "name": "思彤",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "童声",
    },
    {
        "id": "xiaobei",
        "name": "小北",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "萝莉女声",
    },
    {
        "id": "aitong",
        "name": "艾彤",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "童声",
    },
    {
        "id": "aiwei",
        "name": "艾薇",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "萝莉女声",
    },
    {
        "id": "aibao",
        "name": "艾宝",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "萝莉女声",
    },
    {
        "id": "jielidou",
        "name": "杰力豆",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "治愈童声",
    },
    {
        "id": "zhiwei",
        "name": "知薇",
        "type": "child",
        "gender": "child",
        "lang": "zh",
        "desc": "萝莉女声",
    },
    {
        "id": "mashu",
        "name": "马树",
        "type": "child",
        "gender": "male",
        "lang": "zh",
        "desc": "儿童剧男声",
    },
    {
        "id": "yuer",
        "name": "悦儿",
        "type": "child",
        "gender": "female",
        "lang": "zh",
        "desc": "儿童剧女声",
    },
    # 文学场景
    {
        "id": "aiyuan",
        "name": "艾媛",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "知心姐姐",
    },
    {
        "id": "aiying",
        "name": "艾颖",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "软萌童声",
    },
    {
        "id": "aixiang",
        "name": "艾祥",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "磁性男声",
    },
    {
        "id": "aimo",
        "name": "艾墨",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "情感男声",
    },
    {
        "id": "aiye",
        "name": "艾晔",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "青年男声",
    },
    {
        "id": "aiting",
        "name": "艾婷",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "电台女声",
    },
    {
        "id": "aifan",
        "name": "艾凡",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "情感女声",
    },
    {
        "id": "ainan",
        "name": "艾楠",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "广告男声",
    },
    {
        "id": "aihao",
        "name": "艾浩",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "新闻男声",
    },
    {
        "id": "aiming",
        "name": "艾茗",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "诙谐男声",
    },
    {
        "id": "aixiao",
        "name": "艾笑",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "新闻女声",
    },
    {
        "id": "aichu",
        "name": "艾厨",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "口齿伶俐男",
    },
    {
        "id": "aiqian",
        "name": "艾倩",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "新闻女声",
    },
    {
        "id": "aishu",
        "name": "艾树",
        "type": "literature",
        "gender": "male",
        "lang": "zh-en",
        "desc": "新闻男声",
    },
    {
        "id": "airu",
        "name": "艾茹",
        "type": "literature",
        "gender": "female",
        "lang": "zh-en",
        "desc": "新闻女声",
    },
    # 方言场景
    {
        "id": "shanshan",
        "name": "姗姗",
        "type": "dialect",
        "gender": "female",
        "lang": "cantonese",
        "desc": "粤语女声",
    },
    {
        "id": "chuangirl",
        "name": "小玥",
        "type": "dialect",
        "gender": "female",
        "lang": "sichuan",
        "desc": "四川女声",
    },
    {
        "id": "qingqing",
        "name": "青青",
        "type": "dialect",
        "gender": "female",
        "lang": "taiwan",
        "desc": "台湾女声",
    },
    {
        "id": "cuijie",
        "name": "翠姐",
        "type": "dialect",
        "gender": "female",
        "lang": "northeast",
        "desc": "东北女声",
    },
    {
        "id": "xiaoze",
        "name": "小泽",
        "type": "dialect",
        "gender": "male",
        "lang": "hunan",
        "desc": "湖南男声",
    },
    {
        "id": "jiajia",
        "name": "佳佳",
        "type": "dialect",
        "gender": "female",
        "lang": "cantonese",
        "desc": "粤语女声",
    },
    {
        "id": "taozi",
        "name": "桃子",
        "type": "dialect",
        "gender": "female",
        "lang": "cantonese",
        "desc": "粤语女声",
    },
    {
        "id": "dahu",
        "name": "大虎",
        "type": "dialect",
        "gender": "male",
        "lang": "northeast",
        "desc": "东北男声",
    },
    {
        "id": "laotie",
        "name": "老铁",
        "type": "dialect",
        "gender": "male",
        "lang": "northeast",
        "desc": "东北口音",
    },
    {
        "id": "laomei",
        "name": "老妹",
        "type": "dialect",
        "gender": "female",
        "lang": "northeast",
        "desc": "吆喝女声",
    },
    {
        "id": "aikan",
        "name": "艾侃",
        "type": "dialect",
        "gender": "male",
        "lang": "tianjin",
        "desc": "天津男声",
    },
    {
        "id": "zhiqing",
        "name": "知青",
        "type": "dialect",
        "gender": "female",
        "lang": "taiwan",
        "desc": "台湾女声",
    },
    {
        "id": "abin",
        "name": "阿斌",
        "type": "dialect",
        "gender": "male",
        "lang": "cantonese",
        "desc": "粤语男声",
    },
    {
        "id": "kelly",
        "name": "Kelly",
        "type": "dialect",
        "gender": "female",
        "lang": "hk_cantonese",
        "desc": "港式粤语女声",
    },
    # 英文场景
    {
        "id": "harry",
        "name": "Harry",
        "type": "english",
        "gender": "male",
        "lang": "en-gb",
        "desc": "英式男声",
    },
    {
        "id": "abby",
        "name": "Abby",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "andy",
        "name": "Andy",
        "type": "english",
        "gender": "male",
        "lang": "en-us",
        "desc": "美式男声",
    },
    {
        "id": "eric",
        "name": "Eric",
        "type": "english",
        "gender": "male",
        "lang": "en-gb",
        "desc": "英式男声",
    },
    {
        "id": "emily",
        "name": "Emily",
        "type": "english",
        "gender": "female",
        "lang": "en-gb",
        "desc": "英式女声",
    },
    {
        "id": "luna",
        "name": "Luna",
        "type": "english",
        "gender": "female",
        "lang": "en-gb",
        "desc": "英式女声",
    },
    {
        "id": "luca",
        "name": "Luca",
        "type": "english",
        "gender": "male",
        "lang": "en-gb",
        "desc": "英式男声",
    },
    {
        "id": "wendy",
        "name": "Wendy",
        "type": "english",
        "gender": "female",
        "lang": "en-gb",
        "desc": "英式女声",
    },
    {
        "id": "william",
        "name": "William",
        "type": "english",
        "gender": "male",
        "lang": "en-gb",
        "desc": "英式男声",
    },
    {
        "id": "olivia",
        "name": "Olivia",
        "type": "english",
        "gender": "female",
        "lang": "en-gb",
        "desc": "英式女声",
    },
    {
        "id": "lydia",
        "name": "Lydia",
        "type": "english",
        "gender": "female",
        "lang": "en-zh",
        "desc": "中英双语女声",
    },
    {
        "id": "annie",
        "name": "Annie",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "ava",
        "name": "Ava",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "cally",
        "name": "Cally",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "becca",
        "name": "Becca",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式客服女声",
    },
    {
        "id": "betty",
        "name": "Betty",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "beth",
        "name": "Beth",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "cindy",
        "name": "Cindy",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "donna",
        "name": "Donna",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "eva",
        "name": "Eva",
        "type": "english",
        "gender": "female",
        "lang": "en-us",
        "desc": "美式女声",
    },
    {
        "id": "brian",
        "name": "Brian",
        "type": "english",
        "gender": "male",
        "lang": "en-us",
        "desc": "美式男声",
    },
    {
        "id": "david",
        "name": "David",
        "type": "english",
        "gender": "male",
        "lang": "en-us",
        "desc": "美式男声",
    },
    # 多语言场景
    {
        "id": "tomoka",
        "name": "智香",
        "type": "multilang",
        "gender": "female",
        "lang": "ja",
        "desc": "日语女声",
    },
    {
        "id": "tomoya",
        "name": "智也",
        "type": "multilang",
        "gender": "male",
        "lang": "ja",
        "desc": "日语男声",
    },
    {
        "id": "indah",
        "name": "Indah",
        "type": "multilang",
        "gender": "female",
        "lang": "id",
        "desc": "印尼语女声",
    },
    {
        "id": "farah",
        "name": "Farah",
        "type": "multilang",
        "gender": "female",
        "lang": "ms",
        "desc": "马来语女声",
    },
    {
        "id": "tala",
        "name": "Tala",
        "type": "multilang",
        "gender": "female",
        "lang": "tl",
        "desc": "菲律宾语女声",
    },
    {
        "id": "tien",
        "name": "Tien",
        "type": "multilang",
        "gender": "female",
        "lang": "vi",
        "desc": "越南语女声",
    },
    {
        "id": "kyong",
        "name": "Kyong",
        "type": "multilang",
        "gender": "female",
        "lang": "ko",
        "desc": "韩语女声",
    },
    {
        "id": "masha",
        "name": "Masha",
        "type": "multilang",
        "gender": "female",
        "lang": "ru",
        "desc": "俄语女声",
    },
    {
        "id": "camila",
        "name": "Camila",
        "type": "multilang",
        "gender": "female",
        "lang": "es",
        "desc": "西班牙语女声",
    },
    {
        "id": "perla",
        "name": "Perla",
        "type": "multilang",
        "gender": "female",
        "lang": "it",
        "desc": "意大利语女声",
    },
    {
        "id": "clara",
        "name": "Clara",
        "type": "multilang",
        "gender": "female",
        "lang": "fr",
        "desc": "法语女声",
    },
    {
        "id": "hanna",
        "name": "Hanna",
        "type": "multilang",
        "gender": "female",
        "lang": "de",
        "desc": "德语女声",
    },
    {
        "id": "waan",
        "name": "Waan",
        "type": "multilang",
        "gender": "female",
        "lang": "th",
        "desc": "泰语女声",
    },
    # 多情感场景
    {
        "id": "zhifeng_emo",
        "name": "知锋",
        "type": "emotion",
        "gender": "male",
        "lang": "zh-en",
        "desc": "多情感男声",
    },
    {
        "id": "zhibing_emo",
        "name": "知冰",
        "type": "emotion",
        "gender": "male",
        "lang": "zh",
        "desc": "多情感男声",
    },
    {
        "id": "zhimiao_emo",
        "name": "知妙",
        "type": "emotion",
        "gender": "female",
        "lang": "en-zh",
        "desc": "多情感女声",
    },
    {
        "id": "zhimi_emo",
        "name": "知米",
        "type": "emotion",
        "gender": "female",
        "lang": "zh-en",
        "desc": "多情感女声",
    },
    {
        "id": "zhiyan_emo",
        "name": "知燕",
        "type": "emotion",
        "gender": "female",
        "lang": "zh-en",
        "desc": "多情感女声",
    },
    {
        "id": "zhibei_emo",
        "name": "知贝",
        "type": "emotion",
        "gender": "child",
        "lang": "zh-en",
        "desc": "多情感童声",
    },
    {
        "id": "zhitian_emo",
        "name": "知甜",
        "type": "emotion",
        "gender": "female",
        "lang": "zh-en",
        "desc": "多情感女声",
    },
    # 数字人场景
    {
        "id": "zhixiaobai",
        "name": "知小白",
        "type": "digital_human",
        "gender": "female",
        "lang": "zh-en",
        "desc": "对话数字人",
    },
    {
        "id": "zhixiaoxia",
        "name": "知小夏",
        "type": "digital_human",
        "gender": "female",
        "lang": "zh-en",
        "desc": "对话数字人",
    },
    {
        "id": "zhixiaomei",
        "name": "知小妹",
        "type": "digital_human",
        "gender": "female",
        "lang": "zh-en",
        "desc": "直播数字人",
    },
    {
        "id": "zhigui",
        "name": "知柜",
        "type": "digital_human",
        "gender": "female",
        "lang": "zh-en",
        "desc": "直播数字人",
    },
    {
        "id": "zhishuo",
        "name": "知硕",
        "type": "digital_human",
        "gender": "male",
        "lang": "zh-en",
        "desc": "客服数字人",
    },
    {
        "id": "aixia",
        "name": "艾夏",
        "type": "digital_human",
        "gender": "female",
        "lang": "zh-en",
        "desc": "客服数字人",
    },
    # 直播场景
    {
        "id": "xiaoxian",
        "name": "小仙",
        "type": "live",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温暖女声",
    },
    {
        "id": "maoxiaomei",
        "name": "猫小美",
        "type": "live",
        "gender": "female",
        "lang": "zh-en",
        "desc": "元气女声",
    },
    {
        "id": "aifei",
        "name": "艾飞",
        "type": "live",
        "gender": "male",
        "lang": "zh-en",
        "desc": "激昂解说",
    },
    {
        "id": "yaqun",
        "name": "亚群",
        "type": "live",
        "gender": "male",
        "lang": "zh-en",
        "desc": "播报男声",
    },
    {
        "id": "qiaowei",
        "name": "巧薇",
        "type": "live",
        "gender": "female",
        "lang": "zh-en",
        "desc": "播报女声",
    },
    {
        "id": "ailun",
        "name": "艾伦",
        "type": "live",
        "gender": "male",
        "lang": "zh-en",
        "desc": "悬疑解说",
    },
    {
        "id": "zhimao",
        "name": "知猫",
        "type": "live",
        "gender": "female",
        "lang": "zh",
        "desc": "直播女声",
    },
    # 臻品音色 (Ultra-HD)
    {
        "id": "zhiqi",
        "name": "知琪",
        "type": "ultra_hd",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温柔女声",
    },
    {
        "id": "zhichu",
        "name": "知厨",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "口齿伶俐男",
    },
    {
        "id": "zhixiang",
        "name": "知祥",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "磁性男声",
    },
    {
        "id": "zhijia",
        "name": "知佳",
        "type": "ultra_hd",
        "gender": "female",
        "lang": "zh-en",
        "desc": "标准女声",
    },
    {
        "id": "zhinan",
        "name": "知楠",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "广告男声",
    },
    {
        "id": "zhiqian",
        "name": "知倩",
        "type": "ultra_hd",
        "gender": "female",
        "lang": "zh-en",
        "desc": "新闻女声",
    },
    {
        "id": "zhiru",
        "name": "知茹",
        "type": "ultra_hd",
        "gender": "female",
        "lang": "zh-en",
        "desc": "新闻女声",
    },
    {
        "id": "zhide",
        "name": "知德",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "新闻男声",
    },
    {
        "id": "zhifei",
        "name": "知飞",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "激昂解说",
    },
    {
        "id": "zhilun",
        "name": "知伦",
        "type": "ultra_hd",
        "gender": "male",
        "lang": "zh-en",
        "desc": "悬疑解说",
    },
    {
        "id": "zhitian",
        "name": "知甜",
        "type": "ultra_hd",
        "gender": "female",
        "lang": "zh-en",
        "desc": "甜美女声",
    },
    # 通用场景 - 其他
    {
        "id": "guijie",
        "name": "柜姐",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "温暖女声",
    },
    {
        "id": "stella",
        "name": "Stella",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "知性女声",
    },
    {
        "id": "stanley",
        "name": "Stanley",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "沉稳男声",
    },
    {
        "id": "kenny",
        "name": "Kenny",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "沉稳男声",
    },
    {
        "id": "rosa",
        "name": "Rosa",
        "type": "standard",
        "gender": "female",
        "lang": "zh-en",
        "desc": "自然女声",
    },
    {
        "id": "zhiyuan",
        "name": "知媛",
        "type": "standard",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
    {
        "id": "zhiyue",
        "name": "知悦",
        "type": "standard",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
    {
        "id": "zhida",
        "name": "知达",
        "type": "standard",
        "gender": "male",
        "lang": "zh-en",
        "desc": "标准男声",
    },
    {
        "id": "zhistella",
        "name": "知莎",
        "type": "standard",
        "gender": "female",
        "lang": "zh",
        "desc": "标准女声",
    },
]

# Frontend-formatted voice list
ALIYUN_VOICES_FRONTEND = [
    {"value": "xiaoyun", "label": "小云 (女)"},
    {"value": "xiaogang", "label": "小刚 (男)"},
    {"value": "ruoxi", "label": "若兮 (女)"},
    {"value": "siqi", "label": "思琪 (女)"},
    {"value": "sicheng", "label": "思诚 (男)"},
    {"value": "aiqi", "label": "艾琪 (女)"},
    {"value": "aicheng", "label": "艾诚 (男)"},
    {"value": "zhiqi", "label": "知琪 (女)"},
    {"value": "zhixiang", "label": "知祥 (男)"},
    {"value": "zhimi_emo", "label": "知米 (女-多情感)"},
    {"value": "zhifeng_emo", "label": "知锋 (男-多情感)"},
]


class AliyunTTSProvider(BaseTTSProvider):
    """TTS provider using Aliyun Intelligent Speech Interaction RESTful API."""

    @property
    def provider_name(self) -> str:
        return "aliyun"

    def _get_credentials(self) -> tuple:
        """
        Get Aliyun TTS credentials.

        Returns:
            tuple: (appkey, token, region)
        """
        appkey = get_config("ALIYUN_TTS_APPKEY") or ""
        token = get_config("ALIYUN_TTS_TOKEN") or ""
        region = get_config("ALIYUN_TTS_REGION") or "shanghai"
        return appkey, token, region

    def is_configured(self) -> bool:
        """Check if Aliyun TTS is properly configured."""
        appkey, token, _region = self._get_credentials()
        # Per Aliyun NLS RESTful TTS docs, token is required for authentication.
        # It can be provided either as the `token` request parameter or as
        # the `X-NLS-Token` header, but we still need a token value configured.
        return bool(appkey and token)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings from configuration."""
        return VoiceSettings(
            voice_id=get_config("ALIYUN_TTS_VOICE_ID") or "xiaoyun",
            speed=get_config("ALIYUN_TTS_SPEED") or 0,  # -500 to 500, default 0
            pitch=get_config("ALIYUN_TTS_PITCH") or 0,  # -500 to 500, default 0
            emotion="",  # Emotion is set via voice_id for multi-emotion voices
            volume=get_config("ALIYUN_TTS_VOLUME") or 50,  # 0-100, default 50
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            format=get_config("ALIYUN_TTS_FORMAT") or "mp3",
            sample_rate=get_config("ALIYUN_TTS_SAMPLE_RATE") or 16000,
            bitrate=128000,
            channel=1,
        )

    def get_supported_voices(self) -> List[dict]:
        """Get list of supported voices."""
        return ALIYUN_VOICES

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech using Aliyun TTS.

        Args:
            text: Text to synthesize (max 300 characters)
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)
            model: Not used for Aliyun TTS

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Check text length (300 characters limit)
        if len(text) > 300:
            logger.warning(
                f"Text exceeds Aliyun limit ({len(text)} > 300 chars), truncating"
            )
            text = text[:300]

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Get credentials
        appkey, token, region = self._get_credentials()

        if not appkey:
            raise ValueError(
                "Aliyun TTS credentials are not configured. Set ALIYUN_TTS_APPKEY"
            )
        if not token:
            raise ValueError(
                "Aliyun TTS token is not configured. Set ALIYUN_TTS_TOKEN "
                "(see Aliyun NLS docs: Token authentication is required)."
            )

        # Get endpoint URL
        endpoint = ALIYUN_TTS_ENDPOINTS.get(
            region.lower(), ALIYUN_TTS_ENDPOINTS["shanghai"]
        )

        # Map audio format
        audio_format = audio_settings.format.lower()
        if audio_format not in ALIYUN_AUDIO_FORMATS:
            audio_format = "mp3"

        # Use provider-native ranges for Aliyun
        aliyun_speed = (
            int(round(voice_settings.speed)) if voice_settings.speed is not None else 0
        )
        aliyun_speed = max(-500, min(500, aliyun_speed))

        aliyun_pitch = (
            int(round(voice_settings.pitch)) if voice_settings.pitch is not None else 0
        )
        aliyun_pitch = max(-500, min(500, aliyun_pitch))

        aliyun_volume = (
            int(round(voice_settings.volume))
            if voice_settings.volume is not None
            else 50
        )
        aliyun_volume = max(0, min(100, aliyun_volume))

        # Build request payload
        payload = {
            "appkey": appkey,
            "text": text,
            # Token can be passed in the request body (recommended by docs).
            "token": token,
            "format": audio_format,
            "sample_rate": audio_settings.sample_rate,
            "voice": voice_settings.voice_id,
            "volume": aliyun_volume,
            "speech_rate": aliyun_speed,
            "pitch_rate": aliyun_pitch,
        }

        headers = {
            "Content-Type": "application/json",
        }

        # Add token if available
        if token:
            headers["X-NLS-Token"] = token

        logger.debug(
            f"Calling Aliyun TTS API: voice={voice_settings.voice_id}, "
            f"speed={aliyun_speed}, pitch={aliyun_pitch}, vol={aliyun_volume}, "
            f"text_len={len(text)}"
        )

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=60,
            )

            # Check content type to determine if error or audio
            content_type = response.headers.get("Content-Type", "")

            if (
                "audio" in content_type
                or response.status_code == 200
                and "application/json" not in content_type
            ):
                # Success - got audio data
                audio_data = response.content

                # Get request ID from header
                request_id = response.headers.get("X-NLS-RequestId", "")
                if request_id:
                    logger.debug(f"Aliyun TTS request ID: {request_id}")

                # Estimate duration based on audio size
                # For MP3 at 128kbps: ~16KB/s
                bytes_per_ms = 16
                duration_ms = len(audio_data) // bytes_per_ms if bytes_per_ms > 0 else 0

                logger.info(
                    f"Aliyun TTS synthesis completed: "
                    f"size={len(audio_data)} bytes, duration~={duration_ms}ms"
                )

                return TTSResult(
                    audio_data=audio_data,
                    duration_ms=duration_ms,
                    sample_rate=audio_settings.sample_rate,
                    format=audio_format,
                    word_count=len(text),
                )

            else:
                # Error response (JSON)
                try:
                    result = response.json()
                    status = result.get("status", "unknown")
                    message = result.get("message", "Unknown error")
                    task_id = result.get("task_id", "")
                    raise ValueError(
                        f"Aliyun TTS API error {status}: {message} (task_id: {task_id})"
                    )
                except ValueError as e:
                    if "Aliyun TTS API error" in str(e):
                        raise
                    raise ValueError(f"Aliyun TTS API error: {response.text[:200]}")

        except requests.RequestException as e:
            logger.error(f"Aliyun TTS request failed: {e}")
            raise ValueError(f"Aliyun TTS request failed: {e}")

    def get_provider_config(self) -> ProviderConfig:
        """Get Aliyun provider configuration for frontend."""
        return ProviderConfig(
            name="aliyun",
            label="阿里云",
            speed=ParamRange(min=-500, max=500, step=50, default=0),
            pitch=ParamRange(min=-500, max=500, step=50, default=0),
            supports_emotion=False,
            models=[],
            voices=ALIYUN_VOICES_FRONTEND,
            emotions=[],
        )
