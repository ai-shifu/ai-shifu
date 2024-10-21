import { Modal } from "antd"
import EditNameForm from "./EditNameForm";
import { useRef } from "react";
import { useState } from "react";
import EditAccountName from "./EditAccountNameForm";
import EditContactName from "./EditContactForm";
import EditPasswordName from "./EditPasswordForm";



const FormModal = ({formKey, open, onCancel, onAsyncOk})=> {
    const [loading, setLoading] = useState(false);
    const ref = useRef(null);
    const [footerShow, setFooterShow] = useState(false);

    const onInnerAsyncOk = ()=>{
        setLoading(true);

        ref.current.onFinish(ref.current.getFieldsValue()).then(()=>{
            setLoading(false);
            onAsyncOk();
        }).catch(()=>{
            setLoading(false);
        });
    }

    const onFieldsChange  = (changeValues, allValues)=> {
        console.log(changeValues, allValues);
        const haveValue = allValues.some(item => item.value!=="")
        setFooterShow(haveValue?undefined:null);

    }

    const formKeyFormElementMap = {
        editName:<EditNameForm cRef={ref} onFieldsChange={ onFieldsChange}></EditNameForm >,
        accountName:<EditAccountName cRef={ref} onFieldsChange={ onFieldsChange}></EditAccountName >,
        contact:<EditContactName cRef={ref} onFieldsChange={ onFieldsChange}></EditContactName >,
        password:<EditPasswordName cRef={ref} onFieldsChange={ onFieldsChange}></EditPasswordName>
    }
    return (
        <Modal
            footer={footerShow}
            okButtonProps={{loading}}
            cancelButtonProps={{style:{float:"left"}}}
            open={open}
            onOk={onInnerAsyncOk}
            onCancel={onCancel}>
            {formKeyFormElementMap[formKey]}
        </Modal>
    )
}

export default FormModal;
