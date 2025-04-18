from sqlalchemy import create_engine, Column, Integer, String, Text, update
from sqlalchemy.orm import sessionmaker, declarative_base

from init import cfg

# 创建引擎
engine = create_engine(cfg.COOK_CONN_STR)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class ChaptersFollowUpAskPrompt(Base):
    __tablename__ = "chapters_follow_up_ask_prompt"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lark_app_token = Column(String(64), nullable=False)
    lark_table_id = Column(String(32), nullable=False)
    prompt_template = Column(Text, nullable=False)


def update_follow_up_ask_prompt_template(
    lark_app_token, lark_table_id, prompt_template
):
    session = SessionLocal()
    try:
        # 首先尝试更新现有记录
        stmt = (
            update(ChaptersFollowUpAskPrompt)
            .where(
                ChaptersFollowUpAskPrompt.lark_app_token == lark_app_token,
                ChaptersFollowUpAskPrompt.lark_table_id == lark_table_id,
            )
            .values(prompt_template=prompt_template)
        )
        result = session.execute(stmt)

        # 如果没有更新任何记录，则插入新记录
        if result.rowcount == 0:
            new_record = ChaptersFollowUpAskPrompt(
                lark_app_token=lark_app_token,
                lark_table_id=lark_table_id,
                prompt_template=prompt_template,
            )
            session.add(new_record)

        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_follow_up_ask_prompt_template(lark_table_id):
    session = SessionLocal()
    try:
        result = (
            session.query(ChaptersFollowUpAskPrompt.prompt_template)
            .filter(ChaptersFollowUpAskPrompt.lark_table_id == lark_table_id)
            .first()
        )
        return result[0] if result else ""
    finally:
        session.close()


def update_ask_info_from_api(
    lesson_id,
    lesson_ask_prompt,
    lesson_summary,
    lesson_ask_model="qwen2-72b-instruct",
    lesson_ask_count_history=5,
    lesson_ask_count_limit=5,
    base_url=cfg.API_URL,
):
    import requests
    import json

    url = f"{base_url}/lesson/update_ask_info"

    payload = {
        "lesson_id": lesson_id,
        "lesson_ask_prompt": lesson_ask_prompt,
        "lesson_summary": lesson_summary,
        "lesson_ask_model": lesson_ask_model,
        "lesson_ask_count_history": lesson_ask_count_history,
        "lesson_ask_count_limit": lesson_ask_count_limit,
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        result = response.json()

        if result["code"] == 0 and result["message"] == "success":
            print("Update ask info success")
        else:
            print(f"Update ask info failed: {result['message']}")
    except requests.exceptions.RequestException as e:
        print(f"Request Failed: {e}")
