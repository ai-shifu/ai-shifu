import { Form } from 'antd';
import './ForgetPasswordModal.css';
import FormItem from 'antd/es/form/FormItem';
import { useForm } from "antd/es/form/Form";
import { Input } from 'antd';
import { Space,Button } from 'antd';
import { useState } from 'react';
import { resetPassword,requireResetPasswordCode } from '../../../Api/user';
const { Modal } = require("antd");

const Title = ()=>(
    <div className="forget-password-modal_title">
        <img
            className='logo'
            src={require('../../../Assets/logo-03.png')} alt="" />
        <div className="title">
        枕头后台管理系统
        </div>
    </div>
)

const ForgetPasswordModal = ({open, asyncOk, cancel})=>{
    const [form]  = useForm();
    let [verificationButtonText, setVerificationButtonText] = useState("获取验证码");
    let [verificationButtonDisabled, setVerificationButtonDisabled] = useState(false);
    const [loading, setLoading] = useState(false);
    /**
     * @description 点击获取验证码的方法，倒计时
     */
        const onClickGetVerification = async () => {
            await form.validateFields(['email']).then(()=>{
                setVerificationButtonText('59s');
                verificationButtonText = 59;
                requireResetPasswordCode(form.getFieldValue('email')).then(res=>{
                        setVerificationButtonDisabled(true);
                        const interval = setInterval(()=>{
                            if(verificationButtonText>0){
                                verificationButtonText -= 1;
                                setVerificationButtonText(`${verificationButtonText}s`);
                            } else {
                                clearInterval(interval);
                                setVerificationButtonText('获取验证码');
                                setVerificationButtonDisabled(false);
                            }
                        }, 1000);
                    });
            }).catch(err=>{
                console.log(err);
            });
        }
        const onFinish = (value)=>{
            setLoading(true)
            resetPassword(value.email, value.newPassword, value.verificationCode).then(res=>{
                setLoading(false);
            // 调用修改密码的异步操作
                setLoading(false);
                asyncOk();
            }).catch(err=>{
                setLoading(false);
            })
        }
        const onCancel = ()=>{
            cancel();
        }
    return (
    <Modal
        className="forget-password_modal"
        width={400}
        open={open}
        title={<Title></Title>}
        footer={false}
        closeIcon={<></>}>
        <p className='subtitle'>Forget password 🔒</p>
        <p>输入注册邮箱，我们会给您发送验证码帮助您重置密码</p>
        <Form
            form={form}
            onFinish={onFinish}>
            <FormItem
                name="email"
                rules={[{ required: true, message: '请输入邮箱地址!' }]}>
                <Input placeholder='注册邮箱地址'>
                </Input>
            </FormItem>
            <FormItem
                name="verificationCode"
                rules={[{ required: true, message: '请输入验证码!' }]}>
                <Space.Compact
                    style={{width:"100%"}}>
                    <Input placeholder='验证码'>
                    </Input>
                    <Button
                        style={{width:"120px"}}
                        type='primary'
                        disabled={verificationButtonDisabled}
                        onClick={onClickGetVerification}>
                        {verificationButtonText}
                    </Button>
                </Space.Compact>
            </FormItem>
            <FormItem
                name="newPassword"
                rules={[{ required: true, message: '请输入密码!' }]}>
                <Input
                    type="password"
                    placeholder='请输入新密码'>
                </Input>
            </FormItem>
            <FormItem
                name="againPassword"
                rules={[
                    { required: true, message: '请输入密码!' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('newPassword') === value) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error('两次输入不一致'));
                      },
                    }),
                    ]}>
                <Input
                    type="password"
                    placeholder='请再次输入密码'>
                </Input>
            </FormItem>
            <FormItem>
                <Button
                    style={{width:"100%"}}
                    type='primary'
                    htmlType='submit'
                    loading={loading}>
                    立即重置
                </Button>
            </FormItem>
            <FormItem>
                <Button
                    type='link'
                    onClick={onCancel}>
                    《 返回登录
                </Button>
            </FormItem>
        </Form>
    </Modal>);
}

export default ForgetPasswordModal;
