"""
Baidu TTS Provider.

This module provides TTS synthesis using Baidu's Short Text Online Synthesis API.

API Reference:
- Endpoint: https://tsn.baidu.com/text2audio
- Documentation: https://cloud.baidu.com/doc/SPEECH/s/mlbxh7xie
"""

import logging
import requests
import time
import hashlib
from typing import Optional, List
from urllib.parse import quote

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

# Baidu TTS API endpoints
BAIDU_TTS_API_URL = "https://tsn.baidu.com/text2audio"
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

# Baidu audio format mapping
BAIDU_AUDIO_FORMATS = {
    "mp3": 3,
    "pcm-16k": 4,
    "pcm-8k": 5,
    "wav": 6,
}

# Baidu voice IDs - Complete list
# Reference: https://ai.baidu.com/ai-doc/SPEECH/Rluv3uq3d
BAIDU_VOICES = [
    # 基础音库 (Basic - Free)
    {
        "id": "0",
        "name": "度小美",
        "name_en": "Xiaomei",
        "type": "basic",
        "gender": "female",
        "desc": "标准女主播",
    },
    {
        "id": "1",
        "name": "度小宇",
        "name_en": "Xiaoyu",
        "type": "basic",
        "gender": "male",
        "desc": "亲切男声",
    },
    {
        "id": "3",
        "name": "度逍遥",
        "name_en": "Xiaoyao",
        "type": "basic",
        "gender": "male",
        "desc": "情感男声",
    },
    {
        "id": "4",
        "name": "度丫丫",
        "name_en": "Yaya",
        "type": "basic",
        "gender": "child",
        "desc": "童声",
    },
    # 精品音库 (Premium)
    {
        "id": "5",
        "name": "度逍遥",
        "name_en": "Xiaoyao",
        "type": "premium",
        "gender": "male",
        "desc": "情感男声",
    },
    {
        "id": "103",
        "name": "度米朵",
        "name_en": "Miduo",
        "type": "premium",
        "gender": "child",
        "desc": "可爱童声",
    },
    {
        "id": "106",
        "name": "度博文",
        "name_en": "Bowen",
        "type": "premium",
        "gender": "male",
        "desc": "专业男主播",
    },
    {
        "id": "110",
        "name": "度小童",
        "name_en": "Xiaotong",
        "type": "premium",
        "gender": "child",
        "desc": "童声主播",
    },
    {
        "id": "111",
        "name": "度小萌",
        "name_en": "Xiaomeng",
        "type": "premium",
        "gender": "female",
        "desc": "软萌妹子",
    },
    {
        "id": "5003",
        "name": "度逍遥",
        "name_en": "Xiaoyao",
        "type": "premium",
        "gender": "male",
        "desc": "情感男声-臻品",
    },
    {
        "id": "5118",
        "name": "度小鹿",
        "name_en": "Xiaolu",
        "type": "premium",
        "gender": "female",
        "desc": "甜美女声",
    },
    # 臻品音库 (Premium Plus)
    {
        "id": "4003",
        "name": "度逍遥",
        "name_en": "Xiaoyao",
        "type": "premium_plus",
        "gender": "male",
        "desc": "情感男声",
    },
    {
        "id": "4100",
        "name": "度小雯",
        "name_en": "Xiaowen",
        "type": "premium_plus",
        "gender": "female",
        "desc": "活力女主播",
    },
    {
        "id": "4103",
        "name": "度米朵",
        "name_en": "Miduo",
        "type": "premium_plus",
        "gender": "female",
        "desc": "可爱女声",
    },
    {
        "id": "4105",
        "name": "度灵儿",
        "name_en": "Linger",
        "type": "premium_plus",
        "gender": "female",
        "desc": "清激女声",
    },
    {
        "id": "4106",
        "name": "度博文",
        "name_en": "Bowen",
        "type": "premium_plus",
        "gender": "male",
        "desc": "专业男主播",
    },
    {
        "id": "4114",
        "name": "阿龙",
        "name_en": "Along",
        "type": "premium_plus",
        "gender": "male",
        "desc": "说书男声",
    },
    {
        "id": "4115",
        "name": "度小贤",
        "name_en": "Xiaoxian",
        "type": "premium_plus",
        "gender": "male",
        "desc": "电台男主播",
    },
    {
        "id": "4117",
        "name": "度小乔",
        "name_en": "Xiaoqiao",
        "type": "premium_plus",
        "gender": "female",
        "desc": "活泼女声",
    },
    {
        "id": "4119",
        "name": "度小鹿",
        "name_en": "Xiaolu",
        "type": "premium_plus",
        "gender": "female",
        "desc": "甜美女声",
    },
    {
        "id": "4129",
        "name": "度小彦",
        "name_en": "Xiaoyan",
        "type": "premium_plus",
        "gender": "male",
        "desc": "知识男主播",
    },
    {
        "id": "4140",
        "name": "度小新",
        "name_en": "Xiaoxin",
        "type": "premium_plus",
        "gender": "female",
        "desc": "专业女主播",
    },
    {
        "id": "4141",
        "name": "度婉婉",
        "name_en": "Wanwan",
        "type": "premium_plus",
        "gender": "female",
        "desc": "甜美女声",
    },
    {
        "id": "4143",
        "name": "度清风",
        "name_en": "Qingfeng",
        "type": "premium_plus",
        "gender": "male",
        "desc": "配音男声",
    },
    {
        "id": "4144",
        "name": "度姗姗",
        "name_en": "Shanshan",
        "type": "premium_plus",
        "gender": "female",
        "desc": "娱乐女声",
    },
    {
        "id": "4147",
        "name": "度云朵",
        "name_en": "Yunduo",
        "type": "premium_plus",
        "gender": "child",
        "desc": "可爱童声",
    },
    {
        "id": "4148",
        "name": "度小夏",
        "name_en": "Xiaoxia",
        "type": "premium_plus",
        "gender": "female",
        "desc": "甜美女声",
    },
    {
        "id": "4149",
        "name": "度星河",
        "name_en": "Xinghe",
        "type": "premium_plus",
        "gender": "male",
        "desc": "广告男声",
    },
    {
        "id": "4164",
        "name": "度阿肯",
        "name_en": "Aken",
        "type": "premium_plus",
        "gender": "male",
        "desc": "主播男声",
    },
    {
        "id": "4176",
        "name": "度有为",
        "name_en": "Youwei",
        "type": "premium_plus",
        "gender": "male",
        "desc": "磁性男声",
    },
    {
        "id": "4192",
        "name": "度青川",
        "name_en": "Qingchuan",
        "type": "premium_plus",
        "gender": "male",
        "desc": "温柔男声",
    },
    {
        "id": "4206",
        "name": "度博文",
        "name_en": "Bowen",
        "type": "premium_plus",
        "gender": "male",
        "desc": "综艺男声",
    },
    {
        "id": "4226",
        "name": "南方",
        "name_en": "Nanfang",
        "type": "premium_plus",
        "gender": "female",
        "desc": "电台女主播",
    },
    {
        "id": "4254",
        "name": "度小清",
        "name_en": "Xiaoqing",
        "type": "premium_plus",
        "gender": "female",
        "desc": "广告女声",
    },
    {
        "id": "4259",
        "name": "度小新",
        "name_en": "Xiaoxin",
        "type": "premium_plus",
        "gender": "female",
        "desc": "播音女声",
    },
    {
        "id": "4277",
        "name": "西贝",
        "name_en": "Xibei",
        "type": "premium_plus",
        "gender": "female",
        "desc": "脱口秀女声",
    },
    {
        "id": "4278",
        "name": "度小贝",
        "name_en": "Xiaobei",
        "type": "premium_plus",
        "gender": "female",
        "desc": "知识女主播",
    },
    {
        "id": "4288",
        "name": "度晴岚",
        "name_en": "Qinglan",
        "type": "premium_plus",
        "gender": "female",
        "desc": "甜美女声",
    },
    {
        "id": "5147",
        "name": "度常盈",
        "name_en": "Changying",
        "type": "premium_plus",
        "gender": "female",
        "desc": "电台女主播",
    },
    {
        "id": "5153",
        "name": "度常悦",
        "name_en": "Changyue",
        "type": "premium_plus",
        "gender": "female",
        "desc": "民生女主播",
    },
    {
        "id": "5971",
        "name": "度皮特",
        "name_en": "Pete",
        "type": "premium_plus",
        "gender": "male",
        "desc": "老外男声",
    },
    {
        "id": "5976",
        "name": "度小皮",
        "name_en": "Xiaopi",
        "type": "premium_plus",
        "gender": "child",
        "desc": "萌娃童声",
    },
    {
        "id": "6205",
        "name": "度悠然",
        "name_en": "Youran",
        "type": "premium_plus",
        "gender": "male",
        "desc": "旁白男声",
    },
    {
        "id": "6221",
        "name": "度云萱",
        "name_en": "Yunxuan",
        "type": "premium_plus",
        "gender": "female",
        "desc": "旁白女声",
    },
    {
        "id": "6543",
        "name": "度雨萌",
        "name_en": "Yumeng",
        "type": "premium_plus",
        "gender": "female",
        "desc": "邻家女孩",
    },
    {
        "id": "6546",
        "name": "度清豪",
        "name_en": "Qinghao",
        "type": "premium_plus",
        "gender": "male",
        "desc": "逍遥侠客",
    },
    {
        "id": "6561",
        "name": "度小乐",
        "name_en": "Xiaole",
        "type": "premium_plus",
        "gender": "child",
        "desc": "可爱童声",
    },
    {
        "id": "6562",
        "name": "度雨楠",
        "name_en": "Yunan",
        "type": "premium_plus",
        "gender": "female",
        "desc": "元气少女",
    },
    {
        "id": "6602",
        "name": "度清柔",
        "name_en": "Qingrou",
        "type": "premium_plus",
        "gender": "male",
        "desc": "温柔男神",
    },
    {
        "id": "6644",
        "name": "度书宁",
        "name_en": "Shuning",
        "type": "premium_plus",
        "gender": "female",
        "desc": "亲和女声",
    },
    {
        "id": "6746",
        "name": "度书道",
        "name_en": "Shudao",
        "type": "premium_plus",
        "gender": "male",
        "desc": "沉稳男声",
    },
    {
        "id": "6747",
        "name": "度书古",
        "name_en": "Shugu",
        "type": "premium_plus",
        "gender": "male",
        "desc": "情感男声",
    },
    {
        "id": "6748",
        "name": "度书严",
        "name_en": "Shuyan",
        "type": "premium_plus",
        "gender": "male",
        "desc": "沉稳男声",
    },
    # 大模型音库 (Large Model - Ultra Realistic)
    {
        "id": "4146",
        "name": "度禧禧",
        "name_en": "Xixi",
        "type": "large_model",
        "gender": "female",
        "desc": "阳光女声",
    },
    {
        "id": "4156",
        "name": "度言浩",
        "name_en": "Yanhao",
        "type": "large_model",
        "gender": "male",
        "desc": "年轻男声",
    },
    {
        "id": "4157",
        "name": "度言静",
        "name_en": "Yanjing",
        "type": "large_model",
        "gender": "female",
        "desc": "明亮女声",
    },
    {
        "id": "4179",
        "name": "度泽言",
        "name_en": "Zeyan",
        "type": "large_model",
        "gender": "male",
        "desc": "温暖男声",
    },
    {
        "id": "4189",
        "name": "度涵竹",
        "name_en": "Hanzhu",
        "type": "large_model",
        "gender": "female",
        "desc": "开朗女声-多情感",
    },
    {
        "id": "4193",
        "name": "度泽言",
        "name_en": "Zeyan",
        "type": "large_model",
        "gender": "male",
        "desc": "开朗男声-多情感",
    },
    {
        "id": "4194",
        "name": "度嫣然",
        "name_en": "Yanran",
        "type": "large_model",
        "gender": "female",
        "desc": "活泼女声-多情感",
    },
    {
        "id": "4195",
        "name": "度怀安",
        "name_en": "Huaian",
        "type": "large_model",
        "gender": "male",
        "desc": "磁性男声-多情感",
    },
    {
        "id": "4196",
        "name": "度清影",
        "name_en": "Qingying",
        "type": "large_model",
        "gender": "female",
        "desc": "甜美女声-多情感",
    },
    {
        "id": "4197",
        "name": "度沁遥",
        "name_en": "Qinyao",
        "type": "large_model",
        "gender": "female",
        "desc": "知性女声-多情感",
    },
    {
        "id": "6567",
        "name": "度小柔",
        "name_en": "Xiaorou",
        "type": "large_model",
        "gender": "female",
        "desc": "温柔女声",
    },
    # 方言音库 (Dialect Voices)
    {
        "id": "4007",
        "name": "度小台",
        "name_en": "Xiaotai",
        "type": "dialect",
        "gender": "female",
        "desc": "台湾话",
    },
    {
        "id": "4132",
        "name": "度阿闽",
        "name_en": "Amin",
        "type": "dialect",
        "gender": "male",
        "desc": "闽南话",
    },
    {
        "id": "4134",
        "name": "度阿锦",
        "name_en": "Ajin",
        "type": "dialect",
        "gender": "female",
        "desc": "东北话",
    },
    {
        "id": "4139",
        "name": "度小蓉",
        "name_en": "Xiaorong",
        "type": "dialect",
        "gender": "female",
        "desc": "四川话",
    },
    {
        "id": "4150",
        "name": "度湘玉",
        "name_en": "Xiangyu",
        "type": "dialect",
        "gender": "female",
        "desc": "陕西话",
    },
    {
        "id": "4154",
        "name": "度老崔",
        "name_en": "Laocui",
        "type": "dialect",
        "gender": "male",
        "desc": "北京话",
    },
    {
        "id": "4172",
        "name": "度筱林",
        "name_en": "Xiaolin",
        "type": "dialect",
        "gender": "female",
        "desc": "天津话",
    },
    {
        "id": "4257",
        "name": "四川小哥",
        "name_en": "Sichuan",
        "type": "dialect",
        "gender": "male",
        "desc": "四川话",
    },
    {
        "id": "5977",
        "name": "台媒女声",
        "name_en": "Taiwan",
        "type": "dialect",
        "gender": "female",
        "desc": "台湾话",
    },
    {
        "id": "5980",
        "name": "度阿花",
        "name_en": "Ahua",
        "type": "dialect",
        "gender": "female",
        "desc": "上海话",
    },
    {
        "id": "20100",
        "name": "度小粤",
        "name_en": "Xiaoyue",
        "type": "dialect",
        "gender": "female",
        "desc": "粤语",
    },
    {
        "id": "20101",
        "name": "度晓芸",
        "name_en": "Xiaoyun",
        "type": "dialect",
        "gender": "female",
        "desc": "粤语",
    },
]

# Token cache
_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def _get_access_token(api_key: str, secret_key: str) -> str:
    """
    Get Baidu access token using API Key and Secret Key.

    Token is cached and refreshed when expired.
    """
    global _token_cache

    # Check cache
    current_time = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > current_time + 300:
        return _token_cache["access_token"]

    # Request new token
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key,
    }

    try:
        response = requests.post(BAIDU_TOKEN_URL, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown error")
            raise ValueError(f"Failed to get Baidu access token: {error_msg}")

        access_token = result["access_token"]
        expires_in = result.get("expires_in", 2592000)  # Default 30 days

        # Cache the token
        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = current_time + expires_in

        logger.info(f"Baidu access token obtained, expires in {expires_in} seconds")
        return access_token

    except requests.RequestException as e:
        logger.error(f"Failed to get Baidu access token: {e}")
        raise ValueError(f"Failed to get Baidu access token: {e}")


# Frontend-formatted voice list
BAIDU_VOICES_FRONTEND = [
    {"value": "0", "label": "度小美 (女)"},
    {"value": "1", "label": "度小宇 (男)"},
    {"value": "3", "label": "度逍遥 (男)"},
    {"value": "4", "label": "度丫丫 (童声)"},
    {"value": "4119", "label": "度小鹿 (女)"},
    {"value": "4143", "label": "度清风 (男)"},
    {"value": "4147", "label": "度云朵 (童声)"},
    {"value": "4156", "label": "度言浩 (男)"},
    {"value": "4157", "label": "度言静 (女)"},
    {"value": "4189", "label": "度涵竹 (女-多情感)"},
    {"value": "4193", "label": "度泽言 (男-多情感)"},
]


class BaiduTTSProvider(BaseTTSProvider):
    """TTS provider using Baidu Short Text Online Synthesis API."""

    @property
    def provider_name(self) -> str:
        return "baidu"

    def _get_credentials(self) -> tuple:
        """
        Get Baidu TTS credentials.

        Returns:
            tuple: (api_key, secret_key)
        """
        api_key = get_config("BAIDU_TTS_API_KEY") or ""
        secret_key = get_config("BAIDU_TTS_SECRET_KEY") or ""
        return api_key, secret_key

    def is_configured(self) -> bool:
        """Check if Baidu TTS is properly configured."""
        api_key, secret_key = self._get_credentials()
        return bool(api_key and secret_key)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings from configuration."""
        return VoiceSettings(
            voice_id=get_config("BAIDU_TTS_VOICE_ID") or "0",  # Default to Xiaomei
            speed=get_config("BAIDU_TTS_SPEED") or 5,  # 0-15, default 5
            pitch=get_config("BAIDU_TTS_PITCH") or 5,  # 0-15, default 5
            emotion="",  # Baidu doesn't support emotion
            volume=get_config("BAIDU_TTS_VOLUME") or 5,  # 0-15, default 5
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            format=get_config("BAIDU_TTS_FORMAT") or "mp3",
            sample_rate=16000,  # Baidu default
            bitrate=128000,
            channel=1,
        )

    def get_supported_voices(self) -> List[dict]:
        """Get list of supported voices."""
        return BAIDU_VOICES

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech using Baidu TTS.

        Args:
            text: Text to synthesize (max 1024 GBK bytes, ~60 Chinese chars)
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)
            model: Not used for Baidu TTS

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Check text length (1024 GBK bytes limit)
        text_gbk = text.encode("gbk", errors="replace")
        if len(text_gbk) > 1024:
            logger.warning(
                f"Text exceeds Baidu limit ({len(text_gbk)} > 1024 bytes), truncating"
            )
            # Truncate to fit
            text = text_gbk[:1024].decode("gbk", errors="ignore")

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Get credentials
        api_key, secret_key = self._get_credentials()

        if not api_key or not secret_key:
            raise ValueError(
                "Baidu TTS credentials are not configured. "
                "Set BAIDU_TTS_API_KEY and BAIDU_TTS_SECRET_KEY"
            )

        # Get access token
        access_token = _get_access_token(api_key, secret_key)

        # Generate unique client ID
        cuid = hashlib.md5(f"ai-shifu-{api_key}".encode()).hexdigest()[:32]

        # Map audio format
        audio_format = audio_settings.format.lower()
        aue = BAIDU_AUDIO_FORMATS.get(audio_format, 3)  # Default to MP3

        # Map speed/pitch from our 0-2.0 range to Baidu's 0-15 range
        # Our speed: 0.5-2.0 (1.0 = normal) -> Baidu: 0-15 (5 = normal)
        baidu_speed = int(voice_settings.speed * 5) if voice_settings.speed else 5
        baidu_speed = max(0, min(15, baidu_speed))

        baidu_pitch = int(voice_settings.pitch + 5) if voice_settings.pitch else 5
        baidu_pitch = max(0, min(15, baidu_pitch))

        baidu_volume = int(voice_settings.volume * 5) if voice_settings.volume else 5
        baidu_volume = max(0, min(15, baidu_volume))

        # Build request parameters
        # Use double URL encoding for text as recommended by Baidu
        encoded_text = quote(quote(text, safe=""), safe="")

        params = {
            "tex": encoded_text,
            "tok": access_token,
            "cuid": cuid,
            "ctp": 1,  # Client type, fixed to 1
            "lan": "zh",  # Language, fixed to Chinese
            "spd": baidu_speed,
            "pit": baidu_pitch,
            "vol": baidu_volume,
            "per": voice_settings.voice_id,
            "aue": aue,
        }

        logger.debug(
            f"Calling Baidu TTS API: voice={voice_settings.voice_id}, "
            f"spd={baidu_speed}, pit={baidu_pitch}, vol={baidu_volume}, "
            f"text_len={len(text)}"
        )

        try:
            response = requests.post(
                BAIDU_TTS_API_URL,
                params=params,
                timeout=60,
            )

            # Check content type to determine if error or audio
            content_type = response.headers.get("Content-Type", "")

            if "audio" in content_type:
                # Success - got audio data
                audio_data = response.content

                # Estimate duration based on audio size
                # For MP3 at 128kbps: ~16KB/s
                bytes_per_ms = 16  # ~16 bytes per ms at 128kbps
                duration_ms = len(audio_data) // bytes_per_ms if bytes_per_ms > 0 else 0

                logger.info(
                    f"Baidu TTS synthesis completed: "
                    f"size={len(audio_data)} bytes, duration~={duration_ms}ms"
                )

                return TTSResult(
                    audio_data=audio_data,
                    duration_ms=duration_ms,
                    sample_rate=16000,
                    format=audio_format,
                    word_count=len(text),
                )

            else:
                # Error response (JSON)
                try:
                    result = response.json()
                    error_code = result.get("err_no", "unknown")
                    error_msg = result.get("err_msg", "Unknown error")
                    raise ValueError(f"Baidu TTS API error {error_code}: {error_msg}")
                except ValueError:
                    raise ValueError(f"Baidu TTS API error: {response.text[:200]}")

        except requests.RequestException as e:
            logger.error(f"Baidu TTS request failed: {e}")
            raise ValueError(f"Baidu TTS request failed: {e}")

    def get_provider_config(self) -> ProviderConfig:
        """Get Baidu provider configuration for frontend."""
        return ProviderConfig(
            name="baidu",
            label="百度",
            speed=ParamRange(min=0, max=15, step=1, default=5),
            pitch=ParamRange(min=0, max=15, step=1, default=5),
            supports_emotion=False,
            models=[],
            voices=BAIDU_VOICES_FRONTEND,
            emotions=[],
        )
