import React from "react";
import { Form, Input, Row } from "antd";
import { PhoneOutlined } from "@ant-design/icons";
import { Space } from "antd";
import { useForm } from "antd/es/form/Form";
import { useImperativeHandle } from "react";

const EditContactName = ({cRef, onFieldsChange }) => {
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
        <PhoneOutlined style={{ fontSize: 64, color: "#1677ff" }}></PhoneOutlined>
        <h1>手机号和电子邮件</h1>
        <Form
          form={form}
          onFieldsChange={onFieldsChange}>
          <Form.Item name="mobile">
            <Input placeholder="输入你的手机号" />
          </Form.Item>
          <Form.Item name="email">
            <Input placeholder="输入你的电子邮件" />
          </Form.Item>
        </Form>
      </Space>
    </Row>
  );
};

export default EditContactName;
