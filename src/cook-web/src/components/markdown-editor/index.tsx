import { useEffect, useImperativeHandle, useRef, useState } from "react";
import Vditor from "vditor";

import "vditor/dist/index.css";
// import { cn } from "@/lib/utils";
interface EditorProps {
    maxLength?: number;
    disabled?: boolean;
    initValue: string;
    onChange: (value: string, id: string) => void;
    editorRef?: React.RefObject<{
        setValue: (value: string) => void;
        getValue: () => string;
        insertValue: (value: string) => void;
        clearStack: () => void;
    }>;
}
const Editor = (props: EditorProps) => {
    const { disabled, initValue, onChange } = props;
    const idRef = useRef<string>('');
    const [vd, setVd] = useState<Vditor>();
    const onChangeRef = useRef(onChange);
    const editRef = useRef(null)
    // const startProgress = () => {
    //     setShowProgress(true);
    //     // 动态增加progress值
    //     progressTimer.current = setInterval(() => {
    //         setProgress(prevProgress => {
    //             if (prevProgress >= 80) {
    //                 // clearInterval(progressTimer.current);
    //                 return 80;
    //             }
    //             return prevProgress + 1;
    //         });
    //     }, 100);
    // }
    // const stopProgress = () => {
    //     if (!progressTimer.current)
    //         return;
    //     clearInterval(progressTimer.current);
    //     setProgress(100);
    //     setTimeout(() => {
    //         setShowProgress(false);
    //         setProgress(0);
    //     }, 1000)
    // }
    useEffect(() => {
        if (!editRef.current) {
            return;
        }
        const vditor = new Vditor(editRef.current as HTMLElement, {
            value: initValue,
            toolbar: [],
            width: '100%',
            cache: {
                enable: false
            },
            mode: 'wysiwyg',
            // image: {
            //     isPreview: false,
            //     preview: (bom: Element) => {
            //         console.log(bom)
            //     }
            // },
            toolbarConfig: {
                hide: true,
                pin: true
            },
            input(value: string) {
                // if () {
                //     onChange?.(value, idRef.current);
                //     console.log(value)
                // }
                onChangeRef.current(value.trim(), idRef.current);
            },
            after: () => {
                vditor.setValue("");
                setVd(vditor);
            },

        });

        // Clear the effect
        return () => {
            vd?.destroy();
            setVd(undefined);
        };
    }, []);

    useEffect(() => {
        onChangeRef.current = onChange;
    }, [onChange])

    useEffect(() => {
        if (!vd) {
            return;
        }
        if (disabled) {
            vd.disabled();
        } else {
            vd.enable();
        }

    }, [vd, disabled])

    useImperativeHandle(props.editorRef, () => {
        return {
            setValue: (value: string, id: string) => {
                vd?.setValue(value);
                idRef.current = id;
            },
            getValue: () => {
                return vd?.getValue() || ''
            },
            insertValue: (value: string) => {
                vd?.insertValue(value);
            },
            clearStack: () => {
                vd?.clearStack();
            },
            disabled: () => {
                vd?.disabled();
            },
            enable: () => {
                vd?.enable();
            }
        }
    }, [vd]);

    useEffect(() => {
        if (!vd) {
            return;
        }
        vd.setValue(initValue);
    }, [initValue])
    return (
        <div id="vditor" ref={editRef} className="markdown w-full  h-[100px] " />
    );
};

export default Editor;
