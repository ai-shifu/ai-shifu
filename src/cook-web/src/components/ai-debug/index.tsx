import React, { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
    XMarkIcon,
} from "@heroicons/react/24/outline";
import { useShifu } from "@/store";
import CMEditor from '@/components/cm-editor';
import ModelList from '@/components/model-list';
import api from '@/api';
import { ChevronDown, ChevronUp, Copy, Minus, Plus, Trash2 } from "lucide-react";
import { getSiteHost } from "@/config/runtime-config";
import { getToken } from "@/local/local";
import { v4 as uuidv4 } from 'uuid';
import Loading from "../loading";
import { useTranslation } from 'react-i18next';

async function* makeTextSteamLineIterator(reader: ReadableStreamDefaultReader) {
    const utf8Decoder = new TextDecoder("utf-8");
    // let response = await fetch(fileURL);
    // let reader = response.body.getReader();
    let { value: chunk, done: readerDone } = await reader.read();
    chunk = chunk ? utf8Decoder.decode(chunk, { stream: true }) : "";

    const re = /\r\n|\n|\r/gm;
    let startIndex = 0;

    for (; ;) {
        // eslint-disable-next-line prefer-const
        let result = re.exec(chunk);
        if (!result) {
            if (readerDone) {
                break;
            }
            const remainder = chunk.substr(startIndex);
            ({ value: chunk, done: readerDone } = await reader.read());
            chunk =
                remainder + (chunk ? utf8Decoder.decode(chunk, { stream: true }) : "");
            startIndex = re.lastIndex = 0;
            continue;
        }
        yield chunk.substring(startIndex, result.index);
        startIndex = re.lastIndex;
    }
    if (startIndex < chunk.length) {
        // last line didn't end in a newline char
        yield chunk.substr(startIndex);
    }
}


const AIModelDialog = ({ blockId, open, onOpenChange }) => {
    const { t } = useTranslation();
    const SITE_HOST = getSiteHost();
    const {
        blockContentProperties,
        blocks,
        actions
        // profileItemDefinations
    } = useShifu();
    const [systemPrompt, setSystemPrompt] = useState('');
    const [userPrompt, setUserPrompt] = useState('');
    const [systemPromptOpen, setSystemPromptOpen] = useState(false);
    const [userPromptOpen, setUserPromptOpen] = useState(true);
    const [colCount, setColCount] = useState(2);
    const [rowCount, setRowCount] = useState(300);
    const [profiles, setProfiles] = useState([]);
    // const [model, setModel] = useState('');
    const [models, setModels] = useState<{ model: string, temprature: number }[]>([{ model: 'gpt-4o-mini', temprature: 0.7 }]);
    const [results, setResults] = useState<string[]>([]);
    const [runing, setRuning] = useState(false);
    const abortRefs = useRef<AbortController[]>([]);

    const [variables, setVariables] = useState({});
    const init = async () => {
        const block = blocks.find((item) => item.properties.block_id === blockId);
        if (block) {
            const sysPrompt = await api.getSystemPrompt({
                block_id: blockId
            })
            setSystemPrompt(sysPrompt);
            if (block.properties.block_content.type == 'solidcontent') {
                const contentProp = blockContentProperties[blockId];
                setUserPrompt(contentProp.content);
            } else if (block.properties.block_content.type == 'ai') {
                const contentProp = blockContentProperties[blockId];
                setUserPrompt(contentProp.prompt);
                setProfiles(contentProp.profiles);
                setModels([{
                    model: contentProp.model,
                    temprature: contentProp.temprature
                }]);
            }
        }
    }
    const abort = async () => {
        abortRefs.current.forEach((controller) => {
            if (controller) {
                controller.abort();
            }
        });
    }
    const onOpenChangeHandle = (open) => {
        onOpenChange(open);
    }
    const fetchStream = async (url: string, data: any, index: number, rowIndex: number) => {
        try {
            const controller = new AbortController();
            abortRefs.current[rowIndex * colCount + index] = controller;
            const token = await getToken();
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                    "Token": token,
                    "X-Request-ID": uuidv4().replace(/-/g, '')
                },
                body: JSON.stringify(data),
                signal: controller.signal,
            });

            if (!response.body) {
                throw new Error('No response body');
            }

            const reader = response.body.getReader();

            const lines: string[] = [];
            for await (const line of makeTextSteamLineIterator(reader)) {
                if (!(line as string).startsWith("data:")) {
                    continue;
                }
                lines.push(line);
                if (!line || line.includes('[DONE]')) {
                    continue;
                }
                const json: any = line.replace(/^data:/, '');
                const data = JSON.parse(json);
                if (data.type === 'text') {
                    const position = rowIndex * colCount + index;
                    setResults(prev => {
                        const newResults = [...prev];
                        newResults[position] = newResults[position] + data.content;
                        return newResults;
                    })
                } else if (data.type === 'text_end') {
                }
            }

        } catch (error) {
            console.error('Error in fetchStream:', error);
            throw error;
        }
    }
    const onDebug = async () => {
        if (runing) {
            await abort();
            setRuning(false);
            return;
        }
        setResults([]);

        const totalResults = models.length * colCount;
        setResults(new Array(totalResults).fill(''));
        abortRefs.current = new Array(totalResults).fill(null);
        setRuning(true);
        for (let i = 0; i < models.length; i++) {
            const { model, temprature } = models[i];

            const promises = Array.from({ length: colCount }, (_, colIndex) =>
                fetchStream(`${SITE_HOST}/api/llm/debug-prompt`, {
                    "block_id": blockId,
                    "block_model": model,
                    "block_other_conf": {},
                    "block_prompt": userPrompt,
                    "block_system_prompt": systemPrompt,
                    "block_temperature": temprature,
                    "block_variables": variables
                }, colIndex, i)
            );

            await Promise.all(promises);
        }
        setRuning(false);
    }
    const onCopy = (index: number) => {
        const model = models[index];
        setModels([...models, model]);

    }
    const setModel = (index: number, model: string) => {
        const newModels = [...models];
        newModels[index] = {
            ...newModels[index],
            model: model
        };
        setModels(newModels);
    }
    const setTemperature = (index: number, temprature: number) => {
        const newModels = [...models];
        newModels[index] = {
            ...newModels[index],
            temprature: temprature
        };
        setModels(newModels);
    }
    const onRemove = (index: number) => {
        const newModels = [...models];
        newModels.splice(index, 1);
        setModels(newModels);
    }
    const onProfileValue = (name: string, value: string) => {
        setVariables((state) => {
            return {
                ...state,
                [name]: value
            }
        })
    }
    const updateBlock = async () => {
        actions.setBlockContentPropertiesById(blockId, {
            prompt: userPrompt,
        })
        onOpenChange(false);
    }

    useEffect(() => {
        init();
    }, [])
    return (
        <Dialog open={open} onOpenChange={onOpenChangeHandle} >
            <DialogContent className="flex flex-col sm:max-w-[600px] md:max-w-[800px] max-h-[90vh] overflow-y-auto text-sm">
                <div className="absolute right-4 top-4 cursor-pointer">
                    <XMarkIcon className="h-4 w-4" onClick={() => onOpenChange(false)} />
                </div>
                <DialogHeader className="text-center">
                    <DialogTitle className="text-xl font-bold px-2">{t('ai-debug.debug')}</DialogTitle>
                </DialogHeader>
                <div className=" flex-1 space-y-4 overflow-auto px-4">
                    <div className="text-sm font-medium">{t('ai-debug.ai-module-content')}</div>
                    <Collapsible
                        open={systemPromptOpen}
                        onOpenChange={setSystemPromptOpen}
                        className="w-full border rounded-xl bg-gray-50"
                    >
                        <CollapsibleTrigger className="flex justify-between items-center w-full p-3">
                            <span className="text-gray-500">{t('ai-debug.system-prompt')}</span>
                            <div className="flex items-center">
                                <span className="mr-2 text-gray-500">
                                    {systemPromptOpen ? t('ai-debug.collapse') : t('ai-debug.expand')}
                                </span>
                                {systemPromptOpen ?
                                    <ChevronDown className="h-4 w-4" /> :
                                    <ChevronUp className="h-4 w-4" />
                                }
                            </div>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="p-0">
                            <CMEditor
                                profiles={profiles}
                                content={systemPrompt}
                                onChange={setSystemPrompt}
                                isEdit={true}
                            >
                            </CMEditor>
                        </CollapsibleContent>
                    </Collapsible>
                    <Collapsible
                        open={userPromptOpen}
                        onOpenChange={setUserPromptOpen}
                        className="w-full border rounded-xl bg-gray-50"
                    >
                        <CollapsibleTrigger className="flex justify-between items-center w-full p-3">
                            <span className="text-gray-500">{t('ai-debug.user-prompt')}</span>
                            <div className="flex items-center">
                                <span className="mr-2 text-gray-500">
                                    {userPromptOpen ? t('ai-debug.collapse') : t('ai-debug.expand')}
                                </span>
                                {userPromptOpen ?
                                    <ChevronUp className="h-4 w-4" /> :
                                    <ChevronDown className="h-4 w-4" />
                                }
                            </div>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="py-2 overflow-hidden">
                            <CMEditor
                                profiles={profiles}
                                content={userPrompt}
                                onChange={setUserPrompt}
                                isEdit={true}
                            >
                            </CMEditor>
                            <div className="flex flex-row justify-end px-2">
                                <Button variant='ghost'
                                    className="px-2 h-6 text-primary cursor-pointer"
                                    onClick={updateBlock}
                                >
                                    {t('ai-debug.update-to-shifu')}
                                </Button>
                            </div>
                        </CollapsibleContent>
                    </Collapsible>
                    <div className="flex flex-col gap-2">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <div className="mb-1 text-sm">{t('ai-debug.select-model')}</div>
                            </div>

                            <div>
                                <div className="mb-1 text-sm">{t('ai-debug.set-temperature')}</div>
                            </div>
                        </div>
                        {
                            models.map((model, i) => {
                                return (
                                    <div key={model.model + i} className="grid grid-cols-2 gap-4">
                                        <ModelList className="h-8" value={model.model} onChange={setModel.bind(null, i)} />
                                        <div className="flex items-center space-x-2">
                                            <Input
                                                type="text"
                                                value={model.temprature}
                                                onChange={(e) => setTemperature(i, parseFloat(e.target.value))}
                                                // step="0.1"
                                                // min="0"
                                                // max="1"
                                                className="w-full"
                                            />
                                            <Button variant="outline" size="icon" disabled={model.temprature <= 0} className="h-8 w-8 shrink-0"
                                                onClick={() => {
                                                    const val = Number(model.temprature);
                                                    if (val <= 0) {
                                                        setTemperature(i, 0);
                                                        return;
                                                    }
                                                    setTemperature(i, Number((val - 0.1).toFixed(1)))
                                                }}
                                            >
                                                <Minus className="h-4 w-4" />
                                            </Button>
                                            <Button variant="outline" size="icon" disabled={model.temprature >= 1} className="h-8 w-8 shrink-0"
                                                onClick={() => {
                                                    const val = Number(model.temprature);
                                                    if (val >= 1) {
                                                        setTemperature(i, 1)
                                                        return;
                                                    }
                                                    setTemperature(i, Number((val + 0.1).toFixed(1)))
                                                }}
                                            >
                                                <Plus className="h-4 w-4" />
                                            </Button>
                                            <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
                                                onClick={onRemove.bind(null, i)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                            <Button variant="outline" size="icon"
                                                className="h-8 w-8 shrink-0"
                                                onClick={onCopy.bind(null, i)}
                                            >
                                                <Copy className="h-4 w-4" />
                                            </Button>
                                        </div>

                                    </div>

                                )
                            })
                        }
                    </div>
                    <div>
                        {
                            profiles.map((item) => {
                                return (
                                    <div key={item} className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="mb-1 text-sm">{t('ai-debug.variable')}</div>
                                            <Input value={item} readOnly />
                                        </div>
                                        <div>
                                            <div className="mb-1 text-sm">{t('ai-debug.input-variable-value')}</div>
                                            <Input onChange={(e) => onProfileValue(item, e.target.value)} />
                                        </div>
                                    </div>
                                )
                            })
                        }
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="mb-1 text-sm">{t('ai-debug.column-count')}</div>
                            <div className="flex items-center space-x-2">
                                <Input
                                    type="text"
                                    value={colCount}
                                    onChange={(e) => setColCount(parseInt(e.target.value))}
                                    className="w-full"
                                />
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        if (colCount <= 1) {
                                            setColCount(1)
                                            return;
                                        }
                                        setColCount(colCount - 1)
                                    }}
                                >
                                    <Minus className="h-4 w-4" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        setColCount(colCount + 1)
                                    }}
                                >
                                    <Plus className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                        <div>
                            <div className="mb-1 text-sm">{t('ai-debug.row-count')}</div>
                            <div className="flex items-center space-x-2">
                                <Input
                                    type="text"
                                    value={rowCount}
                                    onChange={(e) => setRowCount(parseInt(e.target.value))}
                                    className="w-full"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="mt-6 flex justify-center">
                        <Button className="bg-purple-600 hover:bg-purple-700 text-white w-full" onClick={onDebug}>
                            {
                                !runing && <span>{t('ai-debug.start-debug')}</span>
                            }
                            {
                                runing && (
                                    <span className="flex flex-row items-center">
                                        <Loading className="h-4 w-4 animate-spin mr-1" />
                                        {t('ai-debug.stop-output')}
                                    </span>
                                )
                            }
                        </Button>
                    </div>
                    <div className="flex flex-col gap-4">
                        {models.map((model, modelIndex) => (
                            <div key={model.model + modelIndex} className="space-y-2">
                                <div className="grid gap-4"
                                    style={{
                                        gridTemplateColumns: `repeat(${colCount}, 1fr)`,
                                    }}
                                >
                                    {results.slice(modelIndex * colCount, (modelIndex + 1) * colCount).map((item, i) => (
                                        <div key={i} className="flex flex-col space-y-2 bg-[#F5F5F4] rounded-md p-3">
                                            <div className="text-sm text-gray-500"> {model.model}, {model.temprature}</div>
                                            <div>{item}</div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default AIModelDialog;
