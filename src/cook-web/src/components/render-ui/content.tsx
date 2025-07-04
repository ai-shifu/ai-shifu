
import CMEditor from '@/components/cm-editor';
import { BlockDTO, ContentDTO } from '@/types/shifu';

interface Content {
    id: string;
    properties: BlockDTO;
    isEdit: boolean;
    onChange: (properties: BlockDTO) => void;
    onBlur?: () => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function Content(props: Content) {
    const contentProperties = props.properties.properties as ContentDTO
    return (
        <CMEditor
            content={contentProperties.content}
            isEdit={props.isEdit}
            onBlur={props.onBlur}
            onChange={(value, variables, isEdit) => {
                props.onChange({ ...props.properties, properties: { ...contentProperties, content: value } });
                if (props.onEditChange) {
                    props.onEditChange(isEdit);
                }
            }}
        />
    )
}
