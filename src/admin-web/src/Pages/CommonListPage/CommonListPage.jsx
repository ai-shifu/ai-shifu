import {  Space, Modal } from "antd";
import SearchForm from "./SearchForm";
import CommonListTable from "./CommonListTable";
import { useEffect, useState } from "react";
import EditContactModal from "./Modal/EditContactModal";
import ContactDetailModal from "./Modal/ContactDetailModel";


import { Pagination } from "antd";

import {getViewInfo,queryView} from "../../Api/manager"
import { set } from "store";

const CommonListPage = ({viewName}) => {





  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  /**
   * @description 查询参数
   */
  const params = {};
  const [loading, setLoading] = useState(false);
  const [colum, setColum] = useState([]);
  const [searchParams, setSearchParams] = useState({});
  const [searchDefine,setSearchDefine]=useState({})
  /**
   *@description 点击搜索的方法
   *
   * @param {*} searchParams 搜索表单中的条件
   */
  const onSearch = (searchParams) => {
    setSearchParams(searchParams)
    console.log(searchParams);
    setCurrentPage(1);
  };

  const onReset = (searchParams) => {
    searchParams(searchParams)
    // queryAllContacts();
  };

  useEffect(() => {
    console.log('set view')
    getViewInfo(viewName).then((res) => {
      console.log(res);
      const columns = res.data.items.map((item) => {
        return {
          title: item.lable,
          dataIndex: item.name,
          key: item.name,
        };
      });
      setColum(columns);
      setSearchDefine(res.data.queryinput);

    });
  }, []);
  const [contactInfoList, setContactInfoList] = useState([]);
  /**
   * @description 联系人数据
   */
  const queryAllContacts = () => {
    queryView(viewName,currentPage,pageSize,searchParams)
      .then((res) => {
        setTotal(res.data.total);
        setContactInfoList(res.data.items);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  };
  /**
   * @description 联系人编辑表单 modal 的参数
   */
  const [editContactModalProps, setEditContactModalProps] = useState({
    open: false,
    state: "add",
    detailData: {},
  });

  /**
   * @description 查看联系详情的 Modal 的参数
   */
  const [contactDetailModalProps, setContactDetailModalProps] = useState({
    open: false,
    detailData: {},
  });

  /**
   * @description 点击新建联系人
   */
  const onClickCreateContact = () => {
    setEditContactModalProps({
      detailData: {},
      open: true,
      state: "add",
    });
  };

  /**
   * @description 关闭编辑联系人的 FromModal
   */
  const onEditContactCancel = () => {
    setEditContactModalProps({
      ...editContactModalProps,
      open: false,
    });
  };

  /**
   * @description 编辑联系人内 异步提交操作完成
   */
  const onEditAsyncOk = () => {
    setEditContactModalProps({
      ...editContactModalProps,
      open: false,
    });
    queryAllContacts();
  };

  /**
   *点击表格编辑的方法
   * @param {*} row
   */
  const onClickTableRowEdit = (row) => {
    console.log(row);
    setEditContactModalProps({
      open: true,
      state: "edit",
      detailData: row,
    });
  };

  /**
   *点击表格删除的方法
   *
   * @param {*} row
   */
  const onClickTableRowDelte = (row) => {
    Modal.confirm({
      title: "确认删除？",
      content: <p>删除后不可恢复，请谨慎操作！！！</p>,
      onOk: () => {
        // deleteContact([row.contact_id]).then((res) => {
        //   queryAllContacts();
        // });
      },
    });
  };




  const onTableSelectChange = (selectedRowKeys) => {
    // setContactIds(selectedRowKeys);
  };

  const onPaginationChange = (page, pageSize) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  }

  useEffect(() => {
    queryAllContacts();
  }, [pageSize,currentPage,searchParams]);
  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <SearchForm onSearch={onSearch} onReset={onReset} inputs={searchDefine}></SearchForm>
      <CommonListTable
        dataColumns={colum}
        dataSource={contactInfoList}
        loading={loading}
        onTableSelectChange={onTableSelectChange}
      ></CommonListTable>
      <Pagination pageSize={pageSize} onChange={onPaginationChange} current={currentPage} total={total} ></Pagination>
    </Space>
  );
};
export default CommonListPage;
