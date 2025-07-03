
import CMEditor from '@/components/cm-editor';
import { UIBlockDTO,ContentDTO} from '@/types/shifu';


export default function AI(props: UIBlockDTO) {
    const { data } = props;
    const { content, llm, llm_enabled, llm_temperature } = data.properties as ContentDTO;
    return (
        <CMEditor
            content={content}
            isEdit={props.isEdit}
            // onBlur={props.onBlur}
            onChange={(value, variables, isEdit) => {
                props.onPropertiesChange({ ...data, properties: { ...data.properties, content: value } });
            }}
        />
    )
}
