import React from "react";
import { Form, Input, Row } from "antd";
import { UserOutlined } from "@ant-design/icons";
import { Space } from "antd";
import { useForm } from "antd/es/form/Form";
import { useImperativeHandle } from "react";
import { useEffect } from "react";
import {updateUserInfo, getUserInfo} from '../../../../Api/user';
import store from 'store';
const EditNameForm = ({cRef, onFieldsChange }) => {
  const [form] = useForm();
  const onFinish = (value)=>{
    form.validateFields();
    return new Promise((resolve, reject)=>{
      updateUserInfo(value.name).then(res=>{
        console.log(res);
        getUserInfo().then((res)=>{
          store.set('userInfo', res.data);
          setTimeout(()=>{
            window.location.reload();
          })
        });

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
        <UserOutlined style={{ fontSize: 64, color: "#1677ff" }}></UserOutlined>
        <h1>姓名</h1>
        <Form
          form={form}
          onFieldsChange={onFieldsChange}>
          <Form.Item name="name">
            <Input placeholder="输入你的姓名" />
          </Form.Item>
        </Form>
      </Space>
    </Row>
  );
};

export default EditNameForm;
