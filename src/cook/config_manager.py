import os
import yaml
from dotenv import load_dotenv, find_dotenv
import logging

_ = load_dotenv(find_dotenv())


class ConfigManager:
    def __init__(self, config_filename="config.yml"):
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        # 获取当前文件所在的目录
        self.PROJ_DIR = os.path.dirname(current_file_path)
        print(f"PROJ_DIR: {self.PROJ_DIR}")
        # 构建配置文件的完整路径
        self.config_path = os.path.join(self.PROJ_DIR, config_filename)

        with open(self.config_path, "rb") as f:
            config = yaml.safe_load(f)

            _cfg_simulate_streaming_random_sleep = config[
                "simulate_streaming_random_sleep"
            ]
            self.SIM_STM_MIN = _cfg_simulate_streaming_random_sleep["min"]
            self.SIM_STM_MAX = _cfg_simulate_streaming_random_sleep["max"]

            _cfg_llm = config["llm"]
            # DEFAULT_VENDOR = _cfg_openai['default_vendor']
            self.DEFAULT_MODEL = _cfg_llm["default_model"]
            self.DEFAULT_TMP = _cfg_llm["default_temperature"]
            self.ORIGINAL_DEFAULT_MODEL = _cfg_llm["default_model"]

            self.QIANFAN_MODELS = _cfg_llm["qianfan"]["models"]
            self.QIANFAN_DEF_TMP = _cfg_llm["qianfan"]["default_temperature"]

            self.ZHIPU_MODELS = _cfg_llm["zhipu"]["models"]
            self.ZHIPU_DEF_TMP = _cfg_llm["zhipu"]["default_temperature"]

            self.OPENAI_MODELS = _cfg_llm["openai"]["models"]
            self.OPENAI_ORG = _cfg_llm["openai"]["organization"]
            self.OPENAI_DEF_TMP = _cfg_llm["openai"]["default_temperature"]

            self.DEEPSEEK_MODELS = _cfg_llm["deepseek"]["models"]
            self.DEEPSEEK_DEF_TMP = _cfg_llm["deepseek"]["default_temperature"]

            self.BAILIAN_MODELS = _cfg_llm["bailian"]["models"]
            self.BAILIAN_DEF_TMP = _cfg_llm["bailian"]["default_temperature"]

            self.SUPPORT_MODELS = (
                self.QIANFAN_MODELS
                + self.ZHIPU_MODELS
                + self.OPENAI_MODELS
                + self.DEEPSEEK_MODELS
                + self.BAILIAN_MODELS
            )

            _cfg_lark = config["lark"]
            self.LARK_APP_TOKEN = _cfg_lark["app_token"]
            self.DEF_LARK_TABLE_ID = _cfg_lark["default_table_id"]
            self.DEF_LARK_VIEW_ID = _cfg_lark["default_view_id"]

            _cfg_fileupload = config["fileupload"]
            self.IMG_LOCAL_DIR = _cfg_fileupload["img_local_dir"]
            (
                os.makedirs(self.IMG_LOCAL_DIR)
                if not os.path.exists(self.IMG_LOCAL_DIR)
                else None
            )
            self.IMG_OSS_ANAME = _cfg_fileupload["img_oss_aname"]
            self.IMG_OSS_ENDPOINT = _cfg_fileupload["img_oss_endpoint"]
            self.IMG_OSS_BUCKET = _cfg_fileupload["img_oss_bucket"]

            _cfg_db = config["db"]
            self.SQLITE_DB_PATH = os.path.join(self.PROJ_DIR, _cfg_db["sqlite"]["path"])

            _cfg_api = config["api"]
            self.API_URL = _cfg_api[f'{os.getenv("ENV")}_url']
            self.API_URL_TEST = _cfg_api["test_url"]
            self.API_URL_PROD = _cfg_api["prod_url"]

            _cfg_log = config["log"]
            self.LOG_LEVEL = _cfg_log["level"]
            self.LOG_DIR = _cfg_log["log_dir"]
            os.makedirs(self.LOG_DIR) if not os.path.exists(self.LOG_DIR) else None
            self.LOG_OUT_LEVEL = _cfg_log["out_level"]
            self.LOG_OUT_PATH = _cfg_log["out_path"]
            self.LOG_ERR_LEVEL = _cfg_log["err_level"]
            self.LOG_ERR_PATH = _cfg_log["err_path"]

            self.COOK_CONN_STR = (
                f'mysql+pymysql://{os.getenv("COOK_DB_USERNAME")}:{os.getenv("COOK_DB_PASSWORD")}'
                f'@{os.getenv("COOK_DB_HOST")}:3306/{os.getenv("COOK_DB_DATABASE")}'
            )

        # 添加日志配置
        self.setup_logging()

    def setup_logging(self):
        # 创建一个日志格式器
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 创建一个处理器，输出到指定的日志文件
        out_handler = logging.FileHandler(self.LOG_OUT_PATH)
        out_handler.setLevel(self.LOG_OUT_LEVEL)
        out_handler.setFormatter(formatter)

        # 创建一个处理器，输出错误日志到指定的文件
        err_handler = logging.FileHandler(self.LOG_ERR_PATH)
        err_handler.setLevel(self.LOG_ERR_LEVEL)
        err_handler.setFormatter(formatter)

        # 获取根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(self.LOG_LEVEL)

        # 清除现有的处理器（如果有的话）
        root_logger.handlers = []

        # 添加处理器到根日志记录器
        root_logger.addHandler(out_handler)
        root_logger.addHandler(err_handler)

    def set_default_model(self, model):
        self.DEFAULT_MODEL = model

    def set_qianfan_default_temperature(self, temperature):
        self.QIANFAN_DEF_TMP = temperature

    def set_openai_default_temperature(self, temperature):
        self.OPENAI_DEF_TMP = temperature


if __name__ == "__main__":
    cfg = ConfigManager()
    print(os.getenv("ENV"))
    print(cfg.API_URL)
    print(cfg.SUPPORT_MODELS)
