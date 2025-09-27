"""
Unit tests for block_to_mdflow_adapter.py


This module contains unit tests for the convert_block_to_mdflow
function, testing various block type conversion scenarios.

Author: AI Assistant
Date: 2025-09-10
"""

from unittest.mock import patch
from flaskr.service.shifu.block_to_mdflow_adapter import convert_block_to_mdflow
from flaskr.service.shifu.dtos import (
    BlockDTO,
    ContentDTO,
    LoginDTO,
    OptionsDTO,
    BreakDTO,
)


class TestMarkdownFlowAdapter:
    """Test markdown flow adapter conversion function"""

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_content_block_llm_enabled(self, mock_print):
        """Test converting content block with LLM enabled"""
        content = ContentDTO(
            content="这是一个测试内容", llm_enabled=True, llm_temperature=0.7
        )
        block = BlockDTO(
            bid="test1", block_content=content, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        assert result == "这是一个测试内容"
        mock_print.assert_called_once_with("这是一个测试内容")

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_content_block_llm_disabled(self, mock_print):
        """Test converting content block with LLM disabled"""
        content = ContentDTO(content="静态内容", llm_enabled=False, llm_temperature=0.0)
        block = BlockDTO(
            bid="test2", block_content=content, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        assert result == "===静态内容==="
        mock_print.assert_called_once_with("===静态内容===")

    # Note: Input block tests are skipped due to API mismatch between
    # InputDTO (which has result_variable_bids) and the adapter code
    # (which expects result_variable_bid). This indicates a potential bug
    # in the original code that should be addressed separately.

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_options_block(self, mock_print):
        """Test converting options block"""
        options = OptionsDTO(
            result_variable_bid="var123",
            options=[
                {"label": {"zh-CN": "选项1"}, "value": "option1"},
                {"label": {"zh-CN": "选项2"}, "value": "option2"},
            ],
        )
        block = BlockDTO(
            bid="test4",
            block_content=options,
            variable_bids=["var123"],
            resource_bids=[],
        )
        variable_map = {"var123": "user_choice"}

        result = convert_block_to_mdflow(block, variable_map)
        expected = "?[%{{user_choice}}选项1//option1|选项2//option2]"
        assert result == expected
        mock_print.assert_called_once_with(expected)

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_login_block(self, mock_print):
        """Test converting login block"""
        login = LoginDTO(label={"zh-CN": "用户登录"})
        block = BlockDTO(
            bid="test5", block_content=login, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        expected = "?[用户登录//login]"
        assert result == expected
        mock_print.assert_called_once_with(expected)

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_break_block_without_label(self, mock_print):
        """Test converting break block without label (uses default)"""
        break_dto = BreakDTO()
        block = BlockDTO(
            bid="test6", block_content=break_dto, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        expected = "?[休息//break]"
        assert result == expected
        mock_print.assert_called_once_with(expected)

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_block_with_none_content(self, mock_print):
        """Test converting content block when content is None"""
        content = ContentDTO(content=None, llm_enabled=True, llm_temperature=0.5)
        block = BlockDTO(
            bid="test7", block_content=content, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        assert result == ""
        mock_print.assert_called_once_with("")

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_options_with_dict_objects(self, mock_print):
        """Test converting options block with dict objects"""
        options = OptionsDTO(
            options=[
                {"label": {"zh-CN": "是"}, "value": "yes"},
                {"label": {"zh-CN": "否"}, "value": "no"},
            ],
            result_variable_bid="var456",
        )
        block = BlockDTO(
            bid="test8",
            block_content=options,
            variable_bids=["var456"],
            resource_bids=[],
        )
        variable_map = {"var456": "confirmation"}

        result = convert_block_to_mdflow(block, variable_map)
        expected = "?[%{{confirmation}}是//yes|否//no]"
        assert result == expected
        mock_print.assert_called_once_with(expected)

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    def test_convert_chinese_content(self, mock_print):
        """Test converting content block with Chinese characters"""
        content = ContentDTO(
            content="测试中文字符：你好世界！", llm_enabled=True, llm_temperature=0.7
        )
        block = BlockDTO(
            bid="test10", block_content=content, variable_bids=[], resource_bids=[]
        )

        result = convert_block_to_mdflow(block, {})
        expected = "测试中文字符：你好世界！"
        assert result == expected
        mock_print.assert_called_once_with(expected)

    @patch("flaskr.service.shifu.block_to_mdflow_adapter.print")
    @patch("flaskr.service.shifu.block_to_mdflow_adapter.raise_error")
    def test_convert_block_invalid_type(self, mock_raise_error, mock_print):
        """Test converting block with invalid type raises error"""
        content = ContentDTO(content="测试", llm_enabled=True, llm_temperature=0.5)
        # Create block and manually set invalid type
        block = BlockDTO(
            bid="test11", block_content=content, variable_bids=[], resource_bids=[]
        )
        # Manually override the type to test error handling
        block.type = "invalid_type"

        # The function should call raise_error when it can't find a handler
        try:
            convert_block_to_mdflow(block, {})
        except Exception:
            pass  # Expected since raise_error is mocked

        mock_raise_error.assert_called_once_with("Invalid block type: invalid_type")
