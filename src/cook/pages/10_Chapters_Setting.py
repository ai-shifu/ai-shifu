import time

import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space
from pandas import DataFrame

from models.chapter import *
from tools.auth import login

# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="Chapters Setting",
    page_icon="🧙‍♂️",
)

'# 章节剧本文档管理 📚📜📚 '
"""
> 查看/修改/添加剧本文档，以便调试剧本时选择不同的剧本文档
>
> 🚧 未来推送章节文档到正式环境的功能也会放在这
"""
# '---'


@st.experimental_dialog('✏️ 修改 章节剧本文档')
def edit_chapter(df: DataFrame, chapter_id, staff=False):
    with st.form('edit_row'):
        # df
        # chapter_id


        if staff:
            params = {
                'name': st.text_input('章节名称', df.loc[chapter_id, 'name']),
                'lark_table_id': st.text_input('飞书表格 ID', df.loc[chapter_id, 'lark_table_id']),
                'lark_view_id': st.text_input('飞书表格 ViewID', df.loc[chapter_id, 'lark_view_id']),
                'rank': st.number_input('排序权重', value=df.loc[chapter_id, 'rank']),
            }
        else:
            params = {
                'name': st.text_input('章节名称', df.loc[chapter_id, 'name']),
                'lark_table_id': st.text_input('飞书表格 ID', df.loc[chapter_id, 'lark_table_id']),
                'lark_view_id': st.text_input('飞书表格 ViewID', df.loc[chapter_id, 'lark_view_id']),
                'chapter_type': st.text_input('章节类型', df.loc[chapter_id, 'chapter_type']),
            }
            chapter_id = st.text_input('lesson_no(index)', chapter_id)



        submit_button = st.form_submit_button('提交修改', type='primary', use_container_width=True)
        if submit_button:
            if staff:
                conn = sqlite3.connect(cfg.SQLITE_DB_PATH)
                cursor = conn.cursor()
                c = cursor.execute('UPDATE `chapters` SET name=?, lark_table_id=?, lark_view_id=?, rank=? WHERE id=?',
                                   (params['name'], params['lark_table_id'], params['lark_view_id'], params['rank'],
                                    chapter_id))
                conn.commit()
                conn.close()
                st.rerun()
            else:
                # df.loc[chapter_id] = params
                update_chapter_from_api(
                    params['lark_table_id'],
                    params['lark_view_id'],
                    params['name'],
                    chapter_id,
                    params['chapter_type']
                )
                st.rerun()



@st.experimental_dialog('⚠️ 确认删除吗?')
def delete_chapter(df: DataFrame, chapter_id, staff=False):
    with st.form('delete_row'):
        st.text_input('章节名称', df.loc[chapter_id, 'name'], disabled=True)
        table_id = st.text_input('飞书表格 ID', df.loc[chapter_id, 'lark_table_id'], disabled=True)
        st.text_input('飞书表格 ViewID', df.loc[chapter_id, 'lark_view_id'], disabled=True)
        st.number_input('排序权重', value=df.loc[chapter_id, 'rank'], disabled=True)

        submit_button = st.form_submit_button('确认删除', type='primary', use_container_width=True)
        if submit_button:
            if staff:
                conn = sqlite3.connect(cfg.SQLITE_DB_PATH)
                cursor = conn.cursor()
                c = cursor.execute('DELETE FROM `chapters` WHERE id=?', (chapter_id,))
                conn.commit()
                conn.close()
                st.rerun()
            else:
                delete_chapter_from_api(table_id)
                st.rerun()


def stdf_manage(df, title, has_delete=True):
    st.write(f'### {title}')
    event = st.dataframe(
        df,
        height=None,
        column_order=['id', 'name', 'lark_table_id', 'lark_view_id', 'chapter_type'],
        column_config={
            'id': 'lesson_no',
            'name': '章节名称',
            'lark_table_id': '飞书表格 ID',
            'lark_view_id': '飞书表格 ViewID',
            # 'rank': '排序权重',
            'chapter_type': '章节类型'
        },
        use_container_width=True,
        hide_index=True,
        on_select='rerun',
        selection_mode='single-row',
        key=title
    )

    if event.selection['rows']:
        selected_chapter = df.iloc[event.selection['rows'][0]]
        # selected_chapter
        # selected_chapter.name

        cols = st.columns(3 if has_delete else 2)
        with cols[0]:
            if st.button(f'⬆️ 更新 {selected_chapter["name"]}', use_container_width=True):
                update_chapter_from_api(
                    table_id=selected_chapter['lark_table_id'],
                    view_id = selected_chapter['lark_view_id'],
                    title=selected_chapter['name'],
                    index=selected_chapter.name,
                    lesson_type=selected_chapter['chapter_type']
                )

        with cols[1]:
            if st.button(f'✏️ 修改 {selected_chapter["name"]}', use_container_width=True):
                edit_chapter(df, selected_chapter.name)

        if has_delete:
            with cols[2]:
                if st.button(f'❌ 删除 {selected_chapter["name"]}', use_container_width=True):
                    delete_chapter(df, selected_chapter.name)


# 需要登录
if login():

    # tab1, tab2 = st.tabs(['👩🏻‍🏫 教研平台 ', '👩🏻‍🎓 正式环境 '])

    # with tab1:
    '## 👩🏻‍🏫 教研平台 章节配置'
    df_chapters = DataFrame([chapter.__dict__ for chapter in load_chapters_from_sqlite()])
    # df_chapters 只保留部分列
    df_chapters = df_chapters[['id', 'name', 'lark_table_id', 'lark_view_id', 'rank']]
    df_chapters.set_index('id', inplace=True)
    df_chapters.sort_values('rank', inplace=True)
    event = st.dataframe(
        df_chapters,
        column_config={
            'name': '章节名称',
            'lark_table_id': '飞书表格 ID',
            'lark_view_id': '飞书表格 ViewID',
            'rank': '排序权重',
        },
        use_container_width=True,
        hide_index=True,
        on_select='rerun',
        selection_mode='single-row',
        key='教研平台剧本列表'
    )

    if event.selection['rows']:
        selected_chapter = df_chapters.iloc[event.selection['rows'][0]]

        col1, col2 = st.columns(2)
        with col1:
            if st.button(f'✏️ 修改 {selected_chapter["name"]}', use_container_width=True):
                edit_chapter(df_chapters, int(selected_chapter.name), staff=True)

        with col2:
            if st.button(f'❌ 删除 {selected_chapter["name"]}', use_container_width=True):
                delete_chapter(df_chapters, int(selected_chapter.name), staff=True)

    # 添加 章节剧本文档
    with st.expander('➕ 添加 章节剧本文档'):
        with st.form('add_row'):
            max_rank = df_chapters['rank'].max() if not df_chapters.empty else 0
            params = {
                'name': st.text_input('章节名称'),
                'lark_table_id': st.text_input('飞书表格 ID'),
                'lark_view_id': st.text_input('飞书表格 ViewID', value='vewlGkI2Jp'),
                'rank': st.number_input('排序权重', value=max_rank + 1),
            }

            submit_button = st.form_submit_button('添加', type='primary', use_container_width=True)
            if submit_button:
                conn = sqlite3.connect(cfg.SQLITE_DB_PATH)
                cursor = conn.cursor()
                c = cursor.execute('INSERT INTO `chapters` (name, lark_table_id, lark_view_id, rank) VALUES (?, ?, ?, ?)',
                                   (params['name'], params['lark_table_id'], params['lark_view_id'], params['rank']))
                conn.commit()
                conn.close()
                st.rerun()


    #################################################################################
    # 正式环境
    # with tab2:

    add_vertical_space(3)
    '-----'
    '## 👩🏻‍🎓 正式环境 章节配置'
    '> 章节类型：401-体验课； 402-正式课； 405-隐藏分支课'
    df_chapters_api = DataFrame([chapter.__dict__ for chapter in load_chapters_from_api()])

    if st.button('⬆️🔄 批量全部更新 🔄⬆️', type='primary', use_container_width=True):
        for index, row in df_chapters_api.iterrows():
            update_chapter_from_api(
                table_id=row['lark_table_id'],
                view_id=row['lark_view_id'],
                title=row['name'],
                index=row['id'],
                lesson_type=row['chapter_type']
            )
            time.sleep(0.1)
        st.success('批量更新完成', icon='🎉')

    # 提取出体验章节， chapter_type == 401
    df_chapters_trial = df_chapters_api[df_chapters_api['chapter_type'] == 401]
    df_chapters_trial.set_index('id', inplace=True)

    # 提取出正式章节， chapter_type == 402
    df_chapters_norm = df_chapters_api[df_chapters_api['chapter_type'] == 402]
    df_chapters_norm.set_index('id', inplace=True)

    # 提取出分支章节， chapter_type == 405
    df_chapters_hidden = df_chapters_api[df_chapters_api['chapter_type'] == 405]
    df_chapters_hidden.set_index('id', inplace=True)


    # df_chapters_api.set_index('id', inplace=True)

    # df_chapters_api.sort_values('rank', inplace=True)

    stdf_manage(df_chapters_trial, '体验章节配置', has_delete=False)
    stdf_manage(df_chapters_norm, '正式章节配置')
    stdf_manage(df_chapters_hidden, '隐藏分支章节配置')


