import os

import connectorx as cx
import pandas as pd
from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())
db_url = (
    f'mysql://{os.getenv("UMAMI_DB_USERNAME")}:{os.getenv("UMAMI_DB_PASSWORD")}'
    f'@{os.getenv("UMAMI_DB_HOST")}:3306/{os.getenv("UMAMI_DB_DATABASE")}'
)


def get_trail_script_count():
    sql = """
    select count(*), string_value from umami.event_data where 1=1
        and data_key = 'progress_desc'
    group by string_value;
    """

    df: pd.DataFrame = cx.read_sql(db_url, sql, index_col=None)

    return df


def get_chapter_visit_user_by_start_with(
    start_with, direction="to", start_from="2024-08-19 18:00:00"
):
    sql = f"""
select * from umami.event_data where 1=1
    and website_event_id in (
        select website_event_id from umami.event_data where 1=1
            and website_event_id in (
                select event_id from umami.website_event where 1=1
                    and event_name = 'nav_section_switch'
                    and created_at > '{start_from}'
            )
        and data_key = '{direction}'
        and string_value like '{start_with}%'
    )
    and data_key = 'user_id'
group by string_value;
    """

    df: pd.DataFrame = cx.read_sql(db_url, sql, index_col=None)

    return df


def get_event_num_of_user_and_times(event_name, start_from="2024-08-19 18:00:00"):
    sql = f"""
    select string_value from umami.event_data where 1=1
    and website_event_id in (
        select event_id from umami.website_event where 1=1
            and event_name = '{event_name}'
            and created_at > '2024-08-19 18:00:00'
    )
    and data_key = 'user_id'
    group by string_value;
    """
    user_df: pd.DataFrame = cx.read_sql(db_url, sql, index_col=None)
    user_count = user_df.shape[0]

    sql = f"""
    select event_id from umami.website_event where 1=1
    and event_name = '{event_name}'
    and created_at > '2024-08-19 18:00:00'
    """
    times_df: pd.DataFrame = cx.read_sql(db_url, sql, index_col=None)
    times_count = times_df.shape[0]

    return user_count, times_count


if __name__ == "__main__":
    # df = get_trail_script_count()

    # df = get_chapter_visit_user_by_start_with('07')
    # print(df['string_value'].to_list())

    user_count, times_count = get_event_num_of_user_and_times("nav_top_logo")
