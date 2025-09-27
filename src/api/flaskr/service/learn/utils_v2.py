from flask import Flask
from flaskr.util.uuid import generate_id
from flaskr.service.learn.models import LearnGeneratedBlock


def init_generated_block(
    app: Flask,
    shifu_bid: str,
    outline_item_bid: str,
    progress_record_bid: str,
    user_bid: str,
    block_type: int,
    mdflow: str,
    block_index: int,
) -> LearnGeneratedBlock:
    generated_block: LearnGeneratedBlock = LearnGeneratedBlock()
    generated_block.progress_record_bid = progress_record_bid
    generated_block.user_bid = user_bid
    generated_block.outline_item_bid = outline_item_bid
    generated_block.shifu_bid = shifu_bid
    generated_block.block_bid = ""
    generated_block.type = block_type
    generated_block.generated_block_bid = generate_id(app)
    generated_block.generated_content = ""
    generated_block.status = 1
    generated_block.block_content_conf = mdflow
    generated_block.position = block_index
    return generated_block
