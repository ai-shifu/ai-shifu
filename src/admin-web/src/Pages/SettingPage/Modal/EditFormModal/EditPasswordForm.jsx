import React from "react";
import { Form, Input, Row } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { Space } from "antd";
import { useForm } from "antd/es/form/Form";
import { useImperativeHandle } from "react";
import {updatePassword} from '../../../../Api/user';
import { useEffect } from "react";

const EditPasswordName = ({cRef, onFieldsChange }) => {

  const [form] = useForm();

  const onFinish = async(value)=>{
    await form.validateFields().then();
    return new Promise((resolve, reject)=>{
        updatePassword(value.old_password, value.new_password).then(res=>{
          console.log(res);
          resolve()
        }).catch(()=>{
          reject();
        });
    });

  }

  useEffect(()=>{
    form.resetFields()
  },[form]);

  useImperativeHandle(cRef, () => {
    return {
        onFinish,
        getFieldsValue:form.getFieldsValue,
    };
  });





  return (
    <Row className="form-container" justify="center" style={{ textAlign: "center" }}>
      <Space direction="vertical">
        <LockOutlined style={{ fontSize: 64, color: "#1677ff" }}></LockOutlined>
        <h1>修改密码</h1>
        <Form
          form={form}
          onFieldsChange={onFieldsChange}
          onFinish={onFinish}>
          <Form.Item
            name="old_password"
            rules={[{ required: true, message: '请输入密码!' }]}>
            <Input
              placeholder="输入旧密码"
              type="password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            rules={[{ required: true, message: '请输入密码!' }]}>
            <Input placeholder="输入你的新密码" type="password" />
          </Form.Item>
          <Form.Item
            name="again_password"
            rules={[
              { required: true, message: '请输入密码!' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入不一致'));
                },
              }),
              ]}>
            <Input placeholder="再次输入你的新密码" type="password" />
          </Form.Item>
        </Form>
      </Space>
    </Row>
  );
};

export default EditPasswordName;
