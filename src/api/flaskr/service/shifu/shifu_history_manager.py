from .models import ShifuLogDraftStruct


def get_shifu_history(app, user_id: str, shifu_id: str):
    with app.app_context():
        shifu_history = (
            ShifuLogDraftStruct.query.filter_by(
                ShifuLogDraftStruct.shifu_bid == shifu_id,
            )
            .order_by(ShifuLogDraftStruct.created_at.desc())
            .first()
        )
        return shifu_history


def save_shifu_history(app, user_id: str, shifu_id: str, history: str):
    pass
