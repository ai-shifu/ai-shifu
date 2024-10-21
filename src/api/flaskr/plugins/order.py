from flaskr.service.user.models import User
from flaskr.service.order.consts import (
    BUY_STATUS_TYPES,
    BUY_STATUS_VALUES,
    DISCOUNT_STATUS_TYPES,
    DISCOUNT_STATUS_VALUES,
    DISCOUNT_TYPE_VALUES,
    DISCOUNT_APPLY_TYPE_VALUES,
)
from flaskr.service.order.models import AICourseBuyRecord, DiscountRecord, Discount
from .view.models import (
    INPUT_TYPE_TEXT,
    INPUT_TYPE_NUMBER,
    INPUT_TYPE_DATETIME,
    INPUT_TYPE_OPTIONS,
    InputItem,
    TableColumnItem,
    ViewDef,
    OperationItem,
    OperationType,
)


OrderView = ViewDef(
    "order",
    [
        TableColumnItem("id", "ID"),
        TableColumnItem("record_id", "订单ID"),
        TableColumnItem(
            "user_id", "用户ID", model=User, display="mobile", index_id="user_id"
        ),
        TableColumnItem("course_id", "课程ID"),
        TableColumnItem("price", "订单原价"),
        TableColumnItem("pay_value", "应付金额"),
        TableColumnItem("discount_value", "折扣金额"),
        TableColumnItem("status", "状态", items=BUY_STATUS_VALUES),
        TableColumnItem("created", "创建时间"),
        TableColumnItem("updated", "更新时间"),
    ],
    [
        InputItem("user_id", "用户ID", "like", INPUT_TYPE_TEXT),
        InputItem("course_id", "课程ID", "like", INPUT_TYPE_TEXT),
        InputItem("price", "价格", "like", INPUT_TYPE_TEXT),
        InputItem(
            "status", "状态", "like", INPUT_TYPE_TEXT, input_options=BUY_STATUS_TYPES
        ),
        InputItem("created", "创建时间", "like", INPUT_TYPE_TEXT),
        InputItem("updated", "更新时间", "like", INPUT_TYPE_TEXT),
    ],
    AICourseBuyRecord,
)


DisCountdRecordView = ViewDef(
    "discount",
    [
        TableColumnItem(Discount.discount_id, "ID"),
        TableColumnItem(Discount.discount_code, "折扣码"),
        TableColumnItem(Discount.discount_value, "折扣金额"),
        TableColumnItem(Discount.discount_type, "折扣类型", items=DISCOUNT_TYPE_VALUES),
        TableColumnItem(
            Discount.discount_apply_type, "折扣码类型", items=DISCOUNT_APPLY_TYPE_VALUES
        ),
        TableColumnItem(Discount.discount_start, "开始时间"),
        TableColumnItem(Discount.discount_end, "结束时间"),
        TableColumnItem(Discount.discount_limit, "数量限制"),
        TableColumnItem(Discount.discount_channel, "渠道"),
        TableColumnItem(Discount.discount_count, "生成数量"),
        TableColumnItem(Discount.discount_used, "使用数量"),
        TableColumnItem(Discount.discount_filter, "过滤条件"),
    ],
    [
        InputItem("discount_value", "折扣金额", "like", INPUT_TYPE_TEXT),
        InputItem(
            "discount_type",
            "折扣类型",
            "like",
            INPUT_TYPE_TEXT,
            input_options=DISCOUNT_TYPE_VALUES,
        ),
        InputItem(
            "discount_apply_type",
            "折扣码类型",
            "like",
            INPUT_TYPE_TEXT,
            input_options=DISCOUNT_APPLY_TYPE_VALUES,
        ),
        InputItem("discount_start", "开始时间", "like", INPUT_TYPE_DATETIME),
        InputItem("discount_end", "结束时间", "like", INPUT_TYPE_DATETIME),
    ],
    Discount,
    [
        OperationItem(
            "查看折扣码",
            OperationType.GO_TO_LIST,
            "discountrecord",
            "discountrecord",
            {"discount_id": "discount_id"},
        ),
    ],
    [
        OperationItem(
            "创建折扣码",
            OperationType.OPERATION,
            "create",
            "discountcreate",
            {"discount_code": "discount_code"},
        ),
    ],
)


DisCountRecordView = ViewDef(
    "discountrecord",
    [
        TableColumnItem("id", "ID"),
        TableColumnItem("discount_value", "折扣金额"),
        TableColumnItem(
            "user_id", "用户ID", model=User, display="mobile", index_id="user_id"
        ),
        TableColumnItem("discount_code", "折扣码"),
        TableColumnItem("discount_type", "折扣类型", items=DISCOUNT_TYPE_VALUES),
        TableColumnItem("status", "状态", items=DISCOUNT_STATUS_VALUES),
        TableColumnItem("created", "创建时间"),
        TableColumnItem("updated", "更新时间"),
    ],
    [
        InputItem("discount_value", "折扣金额", "like", INPUT_TYPE_TEXT),
        InputItem(
            "status",
            "状态",
            "like",
            INPUT_TYPE_TEXT,
            input_options=DISCOUNT_STATUS_TYPES,
        ),
    ],
    DiscountRecord,
)


DisCountCreateView = ViewDef(
    "discountcreate",
    [],
    [
        # InputItem("discount_code", "折扣码", "like", INPUT_TYPE_TEXT),
        InputItem("discount_value", "折扣金额", "like", INPUT_TYPE_NUMBER),
        InputItem(
            "discount_type",
            "折扣类型",
            "like",
            INPUT_TYPE_OPTIONS,
            input_options=DISCOUNT_TYPE_VALUES,
        ),
        InputItem(
            "discount_apply_type",
            "折扣码类型",
            "like",
            INPUT_TYPE_OPTIONS,
            input_options=DISCOUNT_APPLY_TYPE_VALUES,
        ),
        InputItem("discount_limit", "数量限制", "like", INPUT_TYPE_NUMBER),
        InputItem("discount_channel", "渠道", "like", INPUT_TYPE_TEXT),
        InputItem("discount_filter", "过滤条件", "like", INPUT_TYPE_TEXT),
        InputItem("discount_start", "开始时间", "like", INPUT_TYPE_DATETIME),
        InputItem("discount_end", "结束时间", "like", INPUT_TYPE_DATETIME),
    ],
    Discount,
    [
        OperationItem(
            "创建折扣码",
            OperationType.OPERATION,
            "create",
            "discount",
            {"discount_code": "discount_code"},
        ),
    ],
)
