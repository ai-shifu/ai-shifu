import logging
import requests
import sqlite3

import streamlit

from init import cfg


LESSON_TYPE_TRIAL = 401
LESSON_TYPE_NORMAL = 402
LESSON_TYPE_EXTEND = 403
LESSON_TYPE_BRANCH = 404
LESSON_TYPE_BRANCH_HIDDEN = 405
LESSON_TYPES = {
    "试用课": LESSON_TYPE_TRIAL,
    "正式课": LESSON_TYPE_NORMAL,
    # "延展课": LESSON_TYPE_EXTEND,
    # "分支课": LESSON_TYPE_BRANCH,
    "隐藏分支课": LESSON_TYPE_BRANCH_HIDDEN,
}


class Chapter:
    def __init__(
        self, id, name, lesson_id, lark_table_id, lark_view_id, rank, chapter_type=None
    ):
        self.id = id
        self.name = name
        self.lesson_id = lesson_id
        self.lark_table_id = lark_table_id
        self.lark_view_id = lark_view_id
        self.rank = rank
        self.chapter_type = chapter_type

    def __repr__(self):
        return f"{self.name}  ({self.lark_table_id})"


def load_chapters_from_api(
    doc_id=cfg.LARK_APP_TOKEN, base_url=cfg.API_URL
) -> tuple[list[Chapter], str]:
    url = f"{base_url}/lesson/get_chatper_info"
    params = {"doc_id": doc_id}

    response = requests.get(url, params=params)
    logging.debug(f"load_chapters_from_api: {url}, {params}")
    logging.info(f"load_chapters_from_api: {response.json()}")

    chapters = []
    coures_id = None
    if response.status_code == 200:
        data = response.json()
        print(data)
        coures_id = data["data"]["course_id"]
        for item in data["data"]["lesson_list"]:
            print(item)
            chapters.append(
                Chapter(
                    id=item["lesson_no"],
                    name=item["lesson_name"],
                    lesson_id=item["lesson_id"],
                    lark_table_id=item["feishu_id"],
                    lark_view_id=cfg.DEF_LARK_VIEW_ID,
                    rank=int(item["lesson_no"]),
                    chapter_type=item["lesson_type"],
                )
            )

    else:
        print(f"Failed to retrieve data: {response.status_code}")

    return chapters, coures_id


def update_chapter_from_api(
    table_id, view_id, title, index, lesson_type, base_url=cfg.API_URL
):
    url = f"{base_url}/lesson/update_lesson"
    params = {
        "doc_id": cfg.LARK_APP_TOKEN,
        "table_id": table_id,
        "view_id": view_id,
        "title": title,
        "index": index,
        "lesson_type": lesson_type,
    }

    response = requests.get(url, params=params)
    logging.debug(f"update_chapter_from_api: {url}, {params}")
    logging.info(f"update_chapter_from_api: {response.json()}")

    if response.status_code == 200:
        print(response.json())
        streamlit.toast(f"《{title}》更新成功", icon="🎉")
    else:
        print(f"Failed to update data: {response.status_code}")
        streamlit.toast(f"《{title}》更新失败，错误码: {response.status_code}", icon="🚨")


def delete_chapter_from_api(table_id, course_id, lesson_no, base_url=cfg.API_URL):
    url = f"{base_url}/lesson/delete_lesson"
    params = {
        # 'doc_id': cfg.LARK_APP_TOKEN,
        # 'table_id': table_id,
        "course_id": course_id,
        "lesson_no": lesson_no,
    }

    response = requests.get(url, params=params)
    logging.debug(f"delete_chapter_from_api: {url}, {params}")
    logging.info(f"delete_chapter_from_api: {response.json()}")

    if response.status_code == 200:
        print(response.json())
        streamlit.toast("删除成功", icon="🎉")
    else:
        print(f"Failed to delete data: {response.status_code}")
        streamlit.toast(f"删除失败，错误码: {response.status_code}", icon="🚨")


if __name__ == "__main__":

    # 从API获取章节信息
    chapters = load_chapters_from_api(
        doc_id="IjfsbaLaQah0Wts1VaDcq0ePnGe", base_url=cfg.API_URL_TEST
    )
    print(chapters)
    print(len(chapters))
    print(chapters[0], chapters[0].lesson_id)

    # 从本地数据库获取
    # chapters = load_chapters_from_sqlite()
    #
    # for chapter in chapters:
    #     print(chapter.id, chapter.name, chapter.lark_table_id, chapter.lark_view_id, chapter.rank)
    #
    # chapters_df = DataFrame([chapter.__dict__ for chapter in chapters])
    # print(chapters_df)

    # # 测试新增章节
    # update_chapter_from_api(
    #     table_id='tblkkj1WaozcngwQ',
    #     title='测试新增分支章节（index不连续）',
    #     index='20',
    #     lesson_type=405
    # )

    # # 测试新增正式章节
    # update_chapter_from_api(
    #     table_id='tbldoFfQAPZjFvzg',
    #     title='测试新增正式章节（index不连续）',
    #     index='23',
    #     lesson_type=402
    # )

    # 测试删除章节
    # delete_chapter_from_api('tblkkj1WaozcngwQ')
    # delete_chapter_from_api('tblQhi1ZutfUhW2T')
