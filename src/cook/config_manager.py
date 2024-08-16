import os
import yaml


class ConfigManager:
    def __init__(self, config_filename='config.yml'):
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        # 获取当前文件所在的目录
        self.PROJ_DIR = os.path.dirname(current_file_path)
        print(f'PROJ_DIR: {self.PROJ_DIR}')
        # 构建配置文件的完整路径
        self.config_path = os.path.join(self.PROJ_DIR, config_filename)

        with open(self.config_path, 'rb') as f:
            config = yaml.safe_load(f)

            _cfg_simulate_streaming_random_sleep = config['simulate_streaming_random_sleep']
            self.SIM_STM_MIN = _cfg_simulate_streaming_random_sleep['min']
            self.SIM_STM_MAX = _cfg_simulate_streaming_random_sleep['max']

            _cfg_llm = config['llm']
            # DEFAULT_VENDOR = _cfg_openai['default_vendor']
            self.DEFAULT_MODEL = _cfg_llm['default_model']
            self.DEFAULT_TMP = _cfg_llm['default_temperature']
            self.ORIGINAL_DEFAULT_MODEL = _cfg_llm['default_model']
            self.QIANFAN_MODELS = _cfg_llm['qianfan']['models']
            self.QIANFAN_DEF_TMP = _cfg_llm['qianfan']['default_temperature']
            self.ZHIPU_MODELS = _cfg_llm['zhipu']['models']
            self.ZHIPU_DEF_TMP = _cfg_llm['zhipu']['default_temperature']
            self.OPENAI_MODELS = _cfg_llm['openai']['models']
            self.OPENAI_ORG = _cfg_llm['openai']['organization']
            self.OPENAI_DEF_TMP = _cfg_llm['openai']['default_temperature']
            self.SUPPORT_MODELS = self.QIANFAN_MODELS + self.ZHIPU_MODELS + self.OPENAI_MODELS

            _cfg_lark = config['lark']
            self.LARK_APP_TOKEN = _cfg_lark['app_token']
            self.DEF_LARK_TABLE_ID = _cfg_lark['default_table_id']
            self.DEF_LARK_VIEW_ID = _cfg_lark['default_view_id']

            _cfg_fileupload = config['fileupload']
            self.IMG_LOCAL_DIR = _cfg_fileupload['img_local_dir']
            os.makedirs(self.IMG_LOCAL_DIR) if not os.path.exists(self.IMG_LOCAL_DIR) else None
            self.IMG_OSS_ANAME = _cfg_fileupload['img_oss_aname']
            self.IMG_OSS_ENDPOINT = _cfg_fileupload['img_oss_endpoint']
            self.IMG_OSS_BUCKET = _cfg_fileupload['img_oss_bucket']

            _cfg_db = config['db']
            self.SQLITE_DB_PATH = os.path.join(self.PROJ_DIR, _cfg_db['sqlite']['path'])

            _cfg_api = config['api']
            self.API_URL = _cfg_api[f'{os.getenv("ENV")}_url']


    def set_default_model(self, model):
        self.DEFAULT_MODEL = model

    def set_qianfan_default_temperature(self, temperature):
        self.QIANFAN_DEF_TMP = temperature

    def set_openai_default_temperature(self, temperature):
        self.OPENAI_DEF_TMP = temperature
