from .models import ShifuDraftHistory


def get_shifu_history(app, user_id: str, shifu_id: str):
    with app.app_context():
        shifu_history = (
            ShifuDraftHistory.query.filter_by(
                ShifuDraftHistory.shifu_bid == shifu_id,
            )
            .order_by(ShifuDraftHistory.created_at.desc())
            .first()
        )
        return shifu_history


def save_shifu_history(app, user_id: str, shifu_id: str, history: str):
    pass
