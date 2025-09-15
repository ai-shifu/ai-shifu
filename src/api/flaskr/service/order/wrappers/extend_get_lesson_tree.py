from flask import Flask
from flaskr.framework.plugin.plugin_manager import extension

from flaskr.service.learn.dtos import AICourseDTO, AILessonAttendDTO
from flaskr.service.order.funs import query_raw_buy_record
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.i18n import _
from flaskr.service.lesson.const import LESSON_TYPE_TRIAL
from decimal import Decimal
from typing import List
from flaskr.service.order.models import BannerInfo as BannerInfoModel


class BannerInfo:
    title: str
    pop_up_title: str
    pop_up_content: str
    pop_up_confirm_text: str
    pop_up_cancel_text: str

    def __init__(
        self,
        title: str,
        pop_up_title: str,
        pop_up_content: str,
        pop_up_confirm_text: str,
        pop_up_cancel_text: str,
    ):
        self.title = title
        self.pop_up_title = pop_up_title
        self.pop_up_content = pop_up_content
        self.pop_up_confirm_text = pop_up_confirm_text
        self.pop_up_cancel_text = pop_up_cancel_text

    def __json__(self):
        return {
            "title": self.title,
            "pop_up_title": self.pop_up_title,
            "pop_up_content": self.pop_up_content,
            "pop_up_confirm_text": self.pop_up_confirm_text,
            "pop_up_cancel_text": self.pop_up_cancel_text,
        }


class LessonBannerInfo:
    banner_info: str
    banner_title: str

    def __init__(self, banner_info: str, banner_title: str):
        self.banner_info = banner_info
        self.banner_title = banner_title

    def __json__(self):
        return {
            "banner_info": self.banner_info,
            "banner_title": self.banner_title,
            "type": "banner",
        }


class ExtendCourseInfo:
    course_id: str
    course_name: str
    teacher_avatar: str
    lessons: list

    def __init__(
        self, course_id: str, parent: AICourseDTO, banner_info: BannerInfo = None
    ):
        self.course_id = course_id
        self.course_name = parent.course_name
        self.teacher_avatar = parent.teacher_avatar
        self.lessons = parent.lessons
        self.banner_info = banner_info

    def __json__(self):
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "teacher_avatar": self.teacher_avatar,
            "lessons": self.lessons,
            "banner_info": self.banner_info,
        }


class ExtendLesson:
    lesson_no: str
    lesson_name: str
    lesson_id: str
    status: str
    children: List[AILessonAttendDTO]
    status_value: int
    updated: bool
    unique_id: str
    lesson_type: int
    banner_info: LessonBannerInfo

    def __init__(self, lesson: AILessonAttendDTO, banner_info: LessonBannerInfo = None):
        self.lesson_no = lesson.lesson_no
        self.lesson_name = lesson.lesson_name
        self.lesson_id = lesson.lesson_id
        self.status = lesson.status
        self.children = lesson.children
        self.status_value = lesson.status_value
        self.updated = lesson.updated
        self.unique_id = lesson.unique_id
        self.lesson_type = lesson.lesson_type
        self.banner_info = banner_info

    def __json__(self):
        return {
            "lesson_no": self.lesson_no,
            "lesson_name": self.lesson_name,
            "lesson_id": self.lesson_id,
            "status": self.status,
            "status_value": self.status_value,
            "children": self.children,
            "updated": self.updated,
            "lesson_type": self.lesson_type,
            "banner_info": self.banner_info,
        }


def get_banner_info(app: Flask, course_id: str):
    banner_info = BannerInfoModel.query.filter(
        BannerInfoModel.course_id == course_id,
        BannerInfoModel.deleted == 0,
    ).first()
    return banner_info


@extension("get_lesson_tree_to_study")
def extend_get_lesson_tree(
    result,
    app: Flask,
    user_id: str,
    course_id: str,
    preview_mode: bool = False,
    **kwargs,
):
    app.logger.info(f"extend_get_lesson_tree: user_id={user_id},course_id={course_id}")
    if isinstance(result, AICourseDTO):
        course_id = result.course_id
        banner_info = get_banner_info(app, course_id)
        add_banner = banner_info and banner_info.show_banner == 1
        add_lesson_banner = banner_info and banner_info.show_lesson_banner == 1

        if not add_banner and not add_lesson_banner:
            return result
        is_paid = result.course_price == Decimal(0)
        if not is_paid:
            buy_record = query_raw_buy_record(app, user_id, course_id)
            is_paid = buy_record and buy_record.status == ORDER_STATUS_SUCCESS

        if not is_paid:
            result = ExtendCourseInfo(course_id, result)
            if add_banner:
                banner_info = BannerInfo(
                    title=_("BANNER.BANNER_TITLE"),
                    pop_up_title=_("BANNER.BANNER_POP_UP_TITLE"),
                    pop_up_content=_("BANNER.BANNER_POP_UP_CONTENT"),
                    pop_up_confirm_text=_("BANNER.BANNER_POP_UP_CONFIRM_TEXT"),
                    pop_up_cancel_text=_("BANNER.BANNER_POP_UP_CANCEL_TEXT"),
                )
                result.banner_info = banner_info
            # add lesson banner info
            if add_lesson_banner:
                chapter_count = len(result.lessons)
                lesson_count = sum([len(lesson.children) for lesson in result.lessons])
                lesson_banner_title = _("BANNER.LESSON_BANNER_TITLE")
                lesson_banner_content = _("BANNER.LESSON_BANNER_CONTENT").format(
                    chapter_count=chapter_count, lesson_count=lesson_count
                )
                lesson_banner_info = LessonBannerInfo(
                    lesson_banner_title, lesson_banner_content
                )
                for index in range(len(result.lessons)):
                    app.logger.info(f"index:{index}")
                    if (
                        index > 0
                        and result.lessons[index].lesson_type != LESSON_TYPE_TRIAL
                        and result.lessons[index - 1].lesson_type == LESSON_TYPE_TRIAL
                    ):
                        result.lessons[index - 1] = ExtendLesson(
                            result.lessons[index - 1], lesson_banner_info
                        )
                        break

    return result
