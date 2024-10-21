import { Form, Row, Avatar } from "antd";
import { Modal } from "antd";
import { Empty } from "antd";
import { Divider } from "antd";
import {UserOutlined } from '@ant-design/icons';
import { useEffect, useState } from "react";



/**
 * @description 处理备注字段没有数据时的
 * @param {*}
 * @returns
 */
const RemarkInfo = ({remark})=>{
    if(remark){
        return (
            {remark}
        )
    } else {
        return (
            <Empty></Empty>
        )
    }
}


const ContactDetailModal = ({open, detailData, onCompleted, onCancel})=>{
    const [contactName,setContactName ] = useState("")
    const [phoneNumbers, setPhoneNumbers] = useState()
    const onOk = ()=>{
        onCompleted(detailData);
    }


    useEffect(()=>{
        setContactName(detailData.name||"")
        setPhoneNumbers(detailData.phoneNumbers);
    },[detailData])

    return (
    <Modal
        forceRender
        title="联系人信息"
        open={open}
        okText="编辑"
        cancelButtonProps={{style:{display:"none"}}}
        onOk={onOk}
        onCancel={onCancel}>
        <Form
            className="detail-form">
            <Form.Item
                wrapperCol={{span:24}}>
                <Row
                    justify="center">
                        {<Avatar
                            style={{fontSize:48}}
                            size={120}
                            src={detailData.avatar}
                            icon={contactName?false:<UserOutlined />}>
                            {contactName.slice(0,1)}
                        </Avatar>}
                </Row>
            </Form.Item>
            <Form.Item
                label="姓名"
                shouldUpdate>
                {
                    ()=>(<span >{detailData.name}</span>)
                }
            </Form.Item>
            <Divider></Divider>


            <Form.List
                name="phoneNumbers">
                {(fields)=>{
                    if(fields.length===0){
                        return (
                            <Form.Item
                                label="联系电话">
                                <span>暂无手机号</span>
                            </Form.Item>
                        )
                    }
                    return(<>
                        {
                            fields.map((field)=>(
                                <Form.Item
                                    label="联系电话">
                                    <span>{field.name}</span>
                                </Form.Item>
                            ))
                        }
                        </>)
                }}
            </Form.List>

            <Divider></Divider>

            <Form.List
                name="emails">
                {(fields)=>{
                    if(fields.length===0){
                        return (
                            <Form.Item
                                label="邮箱地址">
                                <span>暂无邮箱</span>
                            </Form.Item>
                        )
                    }
                    return(<>
                        {
                            fields.map((field)=>(
                                <Form.Item
                                    label="邮箱地址">
                                    <span>{field.name}</span>
                                </Form.Item>
                            ))
                        }
                        </>)
                }}
            </Form.List>

            <Divider></Divider>
            <Form.Item
                label="备注">
                <div className="remark-container">
                    <RemarkInfo
                        remark={detailData.remark}>
                    </RemarkInfo>
                </div>
            </Form.Item>
        </Form>
    </Modal>
    )
}



export default ContactDetailModal;
