import CMEditor from '@/components/cm-editor';
import { ContentDTO, UIBlockDTO } from '@/types/shifu';

export default function SolidContent(props: UIBlockDTO) {
    const { data } = props;
    const { content } = data.properties as ContentDTO;
    return (
        <CMEditor
            content={content}
            isEdit={props.isEdit}
            // onBlur={props.onBlur}
            onChange={(value) => {
                props.onPropertiesChange({ ...props.data, properties: { ...props.data.properties, content: value } });
            }}
        />
    )
}
