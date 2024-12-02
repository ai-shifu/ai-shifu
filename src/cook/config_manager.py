import os
import yaml
from dotenv import load_dotenv, find_dotenv
import logging

_ = load_dotenv(find_dotenv())


class ConfigManager:
    def __init__(self, config_filename="config.yml"):
        current_file_path = os.path.abspath(__file__)
        self.PROJ_DIR = os.path.dirname(current_file_path)
        self.config_path = os.path.join(self.PROJ_DIR, config_filename)

        with open(self.config_path, "rb") as f:
            config = yaml.safe_load(f)

            _cfg_simulate_streaming_random_sleep = config[
                "simulate_streaming_random_sleep"
            ]
            self.SIM_STM_MIN = _cfg_simulate_streaming_random_sleep["min"]
            self.SIM_STM_MAX = _cfg_simulate_streaming_random_sleep["max"]

            _cfg_llm = config["llm"]
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
            self.DEF_LARK_VIEW_ID = _cfg_lark["default_view_id"]

            # img fileupload
            self.IMG_LOCAL_DIR = os.getenv("COOK_IMG_LOCAL_DIR")
            os.makedirs(self.IMG_LOCAL_DIR, exist_ok=True)
            self.IMG_OSS_ANAME = os.getenv("COOK_IMG_OSS_ANAME")
            self.IMG_OSS_ENDPOINT = os.getenv("COOK_IMG_OSS_ENDPOINT")
            self.IMG_OSS_BUCKET = os.getenv("COOK_IMG_OSS_BUCKET")
            self.OSS_ACCESS_KEY_ID = os.getenv("ALIBABA_CLOUD_OSS_ACCESS_KEY_ID")
            self.OSS_ACCESS_KEY_SECRET = os.getenv(
                "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET"
            )

            # api
            self.ENV = os.getenv("COOK_USE_API_ENV")
            self.WEB_URL_TEST = os.getenv("WEB_URL_TEST")
            self.WEB_URL_PROD = os.getenv("WEB_URL_PROD")
            self.API_URL_TEST = self.WEB_URL_TEST + "/api"
            self.API_URL_PROD = self.WEB_URL_PROD + "/api"
            self.API_URL = (
                self.API_URL_TEST if self.ENV == "test" else self.API_URL_PROD
            )

            # log
            self.LOG_LEVEL = os.getenv("COOK_LOG_LEVEL", "DEBUG")
            self.LOG_DIR = os.getenv("COOK_LOG_DIR")
            os.makedirs(self.LOG_DIR, exist_ok=True)
            self.LOG_OUT_LEVEL = os.getenv("COOK_LOG_OUT_LEVEL")
            self.LOG_OUT_PATH = os.getenv("COOK_LOG_OUT_PATH")
            self.LOG_ERR_LEVEL = os.getenv("COOK_LOG_ERR_LEVEL")
            self.LOG_ERR_PATH = os.getenv("COOK_LOG_ERR_PATH")

            self.COOK_CONN_STR = (
                f'mysql+pymysql://{os.getenv("COOK_DB_USERNAME")}:{os.getenv("COOK_DB_PASSWORD")}'
                f'@{os.getenv("COOK_DB_HOST")}:3306/{os.getenv("COOK_DB_DATABASE")}'
            )

        # Add logging configuration
        self.setup_logging()

    def setup_logging(self):
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Create a handler to output to the specified log file
        out_handler = logging.FileHandler(self.LOG_OUT_PATH)
        out_handler.setLevel(self.LOG_OUT_LEVEL)
        out_handler.setFormatter(formatter)

        # Create a handler to output error logs to the specified file
        err_handler = logging.FileHandler(self.LOG_ERR_PATH)
        err_handler.setLevel(self.LOG_ERR_LEVEL)
        err_handler.setFormatter(formatter)

        # Get the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.LOG_LEVEL)

        # Clear existing handlers (if any)
        root_logger.handlers = []

        # Add handlers to the root logger
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
