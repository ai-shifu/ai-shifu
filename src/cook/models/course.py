import streamlit as st
from sqlalchemy import create_engine, select, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

from init import cfg

# Create engine
engine = create_engine(cfg.COOK_CONN_STR)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String(24), nullable=False)
    course_name = Column(String(64), nullable=False)
    lark_app_token = Column(String(64), nullable=False)

    def __repr__(self):
        return f"{self.course_name}  (app_token:{self.lark_app_token}  --by {self.user_name})"


@st.cache_data(show_spinner="Get courses from DB...")
def get_courses_by_user(user_name) -> list[Course]:
    session = SessionLocal()
    try:
        # Query data using SQLAlchemy
        stmt = select(Course).where(Course.user_name == user_name)
        courses = session.execute(stmt).scalars().all()
        return courses
    finally:
        session.close()


def insert_course(user_name, course_name, lark_app_token):
    session = SessionLocal()
    try:
        new_course = Course(
            user_name=user_name, course_name=course_name, lark_app_token=lark_app_token
        )
        session.add(new_course)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    get_courses_by_user.clear()


def del_course_by_course_id(course_id):
    session = SessionLocal()
    try:
        course = session.query(Course).filter(Course.id == course_id).first()
        if course:
            session.delete(course)
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    get_courses_by_user.clear()


def update_course_by_course_id(course_id, user_name, course_name, lark_app_token):
    session = SessionLocal()
    try:
        course = session.query(Course).filter(Course.id == course_id).first()
        if course:
            course.user_name = user_name
            course.course_name = course_name
            course.lark_app_token = lark_app_token
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    get_courses_by_user.clear()


if __name__ == "__main__":
    # print(load_all_courses_from_sqlite())
    # print(load_courses_by_user_from_sqlite('zhangsan'))
    # insert_course('zhangsan', 'Python', '123456')
    # del_course_by_course_id(1)
    # update_course_by_course_id(2, 'zhangsan', 'Python', '123456')
    pass

    # moke 10 courses
    # for i in range(10):
    #     insert_course('zhangsan', f'Python{i}', f'123456{i}')
    #     insert_course('lisi', f'Java{i}', f'123456{i}')
    #     insert_course('wangwu', f'C{i}', f'123456{i}')

    # courses = get_courses_by_user_from_sqlite('kenrick')
    courses = get_courses_by_user("kenrick")
    print(courses)
