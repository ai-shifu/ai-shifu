from .models import ShifuDraftRawContent


def get_shifu_history(app, user_id: str, shifu_id: str):
    with app.app_context():
        shifu_history = (
            ShifuDraftRawContent.query.filter_by(
                ShifuDraftRawContent.shifu_bid == shifu_id,
            )
            .order_by(ShifuDraftRawContent.created_at.desc())
            .first()
        )
        return shifu_history


def save_shifu_history(app, user_id: str, shifu_id: str, history: str):
    pass
