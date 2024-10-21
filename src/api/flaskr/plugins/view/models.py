from enum import Enum
from flask import Flask
from flaskr.service.common.dtos import PageNationDTO
import io
from flask import send_file
from datetime import datetime
from openpyxl import Workbook

INPUT_TYPE_TEXT = "text"
INPUT_TYPE_DATE = "date"
INPUT_TYPE_SELECT = "select"
INPUT_TYPE_NUMBER = "number"
INPUT_TYPE_DATETIME = "datetime"
INPUT_TYPE_TIME = "time"
INPUT_TYPE_CHECKBOX = "checkbox"
INPUT_TYPE_OPTIONS = "options"
INPUT_TYPE_OPERATION = "operation"


VIEW_TYPE_LIST = "list"
VIEW_TYPE_DETAIL = "detail"
VIEW_TYPE_FORM = "form"


# query list info


def get_column_name(column):
    if isinstance(column, str):
        return column
    else:
        return column.name


class TableColumnItem:
    def __init__(
        self,
        column,
        lable,
        items=None,
        model=None,
        display="",
        index_id="",
        display_view=None,
    ):
        self.column = column  # database column name
        self.lable = lable  # table column lable name,display in page
        self.items = items
        self.model = model
        self.display = display
        self.index_id = index_id
        self.display_view = display_view

    def __json__(self):
        return {
            "name": get_column_name(self.column),
            "lable": self.lable,
        }


# query input info
class InputItem:
    def __init__(
        self, column, label, query_type, input_type, input_options=None, input_view=None
    ):
        self.column = column
        self.label = label
        self.query_type = query_type
        self.input_type = input_type
        options = None
        if input_options is not None:
            options = []
            for key in input_options.keys():
                if isinstance(key, str):
                    options.append({"value": input_options.get(key), "label": key})
                elif isinstance(key, int):
                    options.append({"value": key, "label": input_options.get(key)})
        self.input_options = options
        self.input_view = input_view

    def __json__(self):
        return {
            "column": self.column,
            "label": self.label,
            "query_type": self.query_type,
            "input_type": self.input_type,
            "input_options": self.input_options,
        }


views = {}


class OperationType(Enum):
    GO_TO_LIST = "go_to_list"
    GO_TO_DETAIL = "go_to_detail"
    OPERATION = "operation"

    def __json__(self):
        return self.value


class OperationItem:
    def __init__(
        self,
        label,
        operation_type,
        operation_value,
        operation_view,
        operation_map,
        operation_function="",
        operation_api="",
    ):
        self.label = label
        self.operation_type = operation_type
        self.operation_value = operation_value
        self.operation_view = operation_view
        self.operation_map = operation_map
        self.operation_function = operation_function
        self.operation_api = operation_api

    def __json__(self):
        return {
            "label": self.label,
            "operation_type": self.operation_type,
            "operation_value": self.operation_value,
            "operation_view": self.operation_view,
            "operation_map": self.operation_map,
        }


class ViewDef:
    def __init__(
        self,
        name: str,
        items: list[TableColumnItem],
        queryinput: list[InputItem],
        model,
        operation_items: list[OperationItem] = [],
        form_operations: list[OperationItem] = [],
        view_type=VIEW_TYPE_LIST,
    ):
        self.name = name
        self.items = items
        self.model = model
        self.queryinput = queryinput

        for item in self.queryinput:
            if item.input_options is not None:
                if isinstance(item.input_options, dict):
                    input_options = {v: k for k, v in item.input_options.items()}
                    item.input_options = input_options
        self.operation_items = operation_items
        self.form_operations = form_operations
        self.view_type = view_type
        views[name] = self

    def query(
        self, app: Flask, page: int = 1, page_size: int = 20, query=None, sort=None
    ):
        with app.app_context():
            app.logger.info(
                "query: "
                + str(query)  # noqa: W503
                + " page: "  # noqa: W503
                + str(page)  # noqa: W503
                + " page_size: "  # noqa: W503
                + str(page_size)  # noqa: W504 , W503
                + " sort: "
                + str(sort)
            )
            db_query = self.model.query
            if query:
                for key in query.keys():
                    app.logger.info("query key:" + key)
                    if self.queryinput.count(lambda x: x.column == key) > 0:
                        input = next(filter(lambda x: x.column == key, self.queryinput))
                        if input.query_type == "like":
                            db_query = db_query.filter(
                                getattr(self.model, key).like(
                                    "%" + str(query.get(key)) + "%"
                                )
                            )
                        else:
                            db_query = db_query.filter(
                                getattr(self.model, key) == query.get(key)
                            )
                    elif getattr(self.model, key):
                        db_query = db_query.filter(
                            getattr(self.model, key) == query.get(key)
                        )

            count = db_query.count()
            if count == 0:
                return {}

            if sort and len(sort) > 0:
                for sort_item in sort:
                    if sort_item.get("order") == "ascend":
                        db_query = db_query.order_by(
                            getattr(self.model, sort_item.get("column")).asc()
                        )
                    else:
                        db_query = db_query.order_by(
                            getattr(self.model, sort_item.get("column")).desc()
                        )
            else:
                db_query = db_query.order_by(self.model.id.desc())
            datas = db_query.offset((page - 1) * page_size).limit(page_size)
            items = [
                {
                    "id": data.id,
                    **{
                        get_column_name(item.column): (
                            item.items.get(
                                getattr(data, get_column_name(item.column)), ""
                            )
                            if item.items
                            else str(getattr(data, get_column_name(item.column)))
                        )
                        for item in self.items
                    },
                }
                for data in datas
            ]

            # 筛选出带有 model 和 display 属性的列
            model_display_items = [
                item
                for item in self.items
                if item.model and item.display and item.index_id
            ]

            for sub_item in model_display_items:
                model = sub_item.model
                column = sub_item.index_id
                query_filters = [
                    str(getattr(data, get_column_name(sub_item.column)))
                    for data in datas
                ]
                app.logger.info(
                    "sub query,model:{},column:{},filter{}".format(
                        model.__class__, column, query_filters
                    )
                )
                model_data = model.query.filter(
                    getattr(model, column).in_(query_filters)
                ).all()
                app.logger.info("{}".format(model_data))
                for item in items:
                    data_items = [
                        data
                        for data in model_data
                        if getattr(data, column) == item[column]
                    ]
                    if len(data_items) > 0:
                        item[column] = getattr(data_items[0], sub_item.display)
                pass

            app.logger.info("query done" + str(items))
            return PageNationDTO(page, page_size, count, items)

    def query_by_id(self, app: Flask, id):
        with app.app_context():
            app.logger.info("query_by_id:" + str(id))
            data = self.model.query.filter_by(id=id).first()
            if data is None:
                return {}
            item = {
                "id": data.id,
                "data": {
                    item.lable: str(getattr(data, get_column_name(item.display)))
                    for item in self.items
                },
            }
            return item

    def query_by_id_and_property(self, app: Flask, id, property):
        with app.app_context():
            app.logger.info("query_by_id:" + str(id))
            data = self.model.query.filter_by(id=id).first()
            property_value = getattr(data, property)
            if property_value is None:
                return {}
            return data

    def export_query_to_excel(self, app: Flask, query=None):

        with app.app_context():
            app.logger.info("export_query_to_excel:" + str(query))
            page = 1
            page_size = 100
            all_items = []

            while True:
                resp = self.query(app, page, page_size, query=query)
                if resp.data is None:
                    break
                if len(resp.data) == 0:
                    break
                all_items.extend(resp.data)
                page += 1

            # create excel
            wb = Workbook()
            ws = wb.active
            ws.title = "Sheet1"

            # write excel header
            if all_items:
                headers = all_items[0].keys()
                headers = list(headers)
                app.logger.info("headers:" + str(headers))
                ws.append(headers)

            # write excel data
            for item in all_items:
                values = list(item.values())
                ws.append(values)
            # save excel to byte stream
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)  # reset stream position
            return send_file(
                path_or_file=output,
                as_attachment=True,
                download_name="export-"
                + datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                + ".xlsx",
            )

    def get_view_def(self):
        return {
            "name": self.name,
            "items": self.items,
            "queryinput": self.queryinput,
            "operation_items": self.operation_items,
            "form_operation": self.form_operations,
        }
