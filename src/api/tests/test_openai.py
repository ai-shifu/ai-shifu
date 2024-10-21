def testopenai(app):
    app.logger.info("testopenai")
    from pydantic import BaseModel
    from openai import OpenAI
    import openai

    app.logger.info(openai.__version__)

    client = OpenAI()

    class CalendarEvent(BaseModel):
        name: str
        date: str
        address: str
        participants: list[str]

    completion = client.beta.chat.completions.parse(  # 使用 beta 接口
        model="gpt-4o-mini-2024-07-18",  # 必须是版本大于 gpt-4o-mini-2024-07-18 或 gpt-4o-2024-08-06 的模型
        messages=[
            {"role": "system", "content": "解析出事件信息。"},
            {
                "role": "user",
                "content": "一般在周一晚上，孙志岗会在他的视频号邀请一名 AI 全栈工程师课程的学员连麦直播。",
            },
        ],
        response_format=CalendarEvent,
    )
    event = completion.choices[0].message.parsed
    app.logger.info(event)
