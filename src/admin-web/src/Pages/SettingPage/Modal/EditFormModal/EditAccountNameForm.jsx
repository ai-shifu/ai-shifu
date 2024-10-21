import React from "react";
import { Form, Input, Row } from "antd";
import { ContactsOutlined } from "@ant-design/icons";
import { Space } from "antd";
import { useForm } from "antd/es/form/Form";
import { useImperativeHandle } from "react";

const EditAccountName = ({cRef, onFieldsChange }) => {
  const [form] = useForm();
  const onFinish = async()=>{

    return new Promise((resolve, reject)=>{
        setTimeout(()=>{
            resolve()
        }, 1000);
    });

  }

  useImperativeHandle(cRef, () => {
    return {
        onFinish,
    };
  });





  return (
    <Row className="form-container" justify="center" style={{ textAlign: "center" }}>
      <Space direction="vertical">
        <ContactsOutlined style={{ fontSize: 64, color: "#1677ff" }}></ContactsOutlined>
        <h1>账号名称</h1>
        <Form
          form={form}
          onFieldsChange={onFieldsChange}>
          <Form.Item name="accountName">
            <Input placeholder="输入你的账号名称" />
          </Form.Item>
        </Form>
      </Space>
    </Row>
  );
};

export default EditAccountName;
