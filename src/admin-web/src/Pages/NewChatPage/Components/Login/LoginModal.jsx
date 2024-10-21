import { Modal, Input } from 'antd';

const LoginModal = ({ open }) => {
  return (<Modal open={open} footer={null} title="登录">
    <div>
      <Input placeholder="请输入手机号" />
    </div>
  </Modal>)
}
