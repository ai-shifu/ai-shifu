import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
    XMarkIcon,
    ChevronDownIcon,
    ChevronUpIcon,
    TrashIcon,
    ClipboardDocumentIcon,
    MinusIcon,
    PlusIcon
} from "@heroicons/react/24/outline";
import { useScenario } from "@/store";
import MDXEditor from '@/components/text-editor';
import ModelList from '@/components/model-list';


const AIModelDialog = ({ blockId, open, onOpenChange }) => {
    const {
        blocks,
    } = useScenario();
    const [systemPrompt, setSystemPrompt] = useState('');
    const [userPrompt, setUserPrompt] = useState('');
    const [systemPromptOpen, setSystemPromptOpen] = useState(false);
    const [userPromptOpen, setUserPromptOpen] = useState(true);
    const [temperature, setTemperature] = useState(0.8);
    const [rowCount, setRowCount] = useState(2);
    const [profiles, setProfiles] = useState([]);
    const [model, setModel] = useState('')
    const init = () => {
        const block = blocks.find((item) => item.properties.block_id === blockId);
        if (block) {
            if (block.properties.block_content.type == 'systemprompt') {
                setSystemPrompt(block.properties.block_content.properties.prompt);
            } else if (block.properties.block_content.type == 'solidcontent') {
                setUserPrompt(block.properties.block_content.properties.content);
            } else if (block.properties.block_content.type == 'ai') {
                setUserPrompt(block.properties.block_content.properties.prompt);
                setTemperature(block.properties.block_content.properties.temprature);
                setProfiles(block.properties.block_content.properties.profiles);
                setModel(block.properties.block_content.properties.model)
                console.log(block.properties.block_content)
            }
            // setSystemPrompt(block.properties.block_content);
        }
        // Search from the current block upwards until the first systemprompt block is found
        const index = blocks.findIndex((item) => item.properties.block_id === blockId);
        for (let i = index - 1; i >= 0; i--) {
            if (blocks[i].properties.block_content.type === 'systemprompt') {
                setSystemPrompt(blocks[i].properties.block_content.properties.prompt);
                break;
            }
        }
    }
    const onOpenChangeHandle = (open) => {
        onOpenChange(open);
    }
    useEffect(() => {
        init();
    }, [])
    return (
        <Dialog open={open} onOpenChange={onOpenChangeHandle} >
            <DialogContent className="flex flex-col sm:max-w-[600px] max-h-[90vh] overflow-y-auto text-sm">
                <div className="absolute right-4 top-4 cursor-pointer">
                    <XMarkIcon className="h-4 w-4" onClick={() => onOpenChange(false)} />
                </div>
                <DialogHeader className="text-center">
                    <DialogTitle className="text-xl font-bold px-2">调试AI模版</DialogTitle>
                </DialogHeader>
                <div className=" flex-1 space-y-4 overflow-auto px-4">
                    {/* Script Information */}


                    {/* AI Module Content */}
                    <div className="text-sm font-medium">AI Module Content:</div>

                    {/* System Prompt */}
                    <Collapsible
                        open={systemPromptOpen}
                        onOpenChange={setSystemPromptOpen}
                        className="w-full border rounded-xl bg-gray-50"
                    >
                        <CollapsibleTrigger className="flex justify-between items-center w-full p-3">
                            <span className="text-gray-500">#系统提示词</span>
                            <div className="flex items-center">
                                <span className="mr-2 text-gray-500">
                                    {systemPromptOpen ? "展开" : "收起"}
                                </span>
                                {systemPromptOpen ?
                                    <ChevronDownIcon className="h-4 w-4" /> :
                                    <ChevronUpIcon className="h-4 w-4" />
                                }
                            </div>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="p-0">
                            {/* System Prompt Content */}
                            <MDXEditor
                                profiles={profiles}
                                content={systemPrompt}
                                onChange={setSystemPrompt}
                                isEdit={true}
                            >

                            </MDXEditor>

                        </CollapsibleContent>
                    </Collapsible>

                    {/* User Prompt */}
                    <Collapsible
                        open={userPromptOpen}
                        onOpenChange={setUserPromptOpen}
                        className="w-full border rounded-xl bg-gray-50"
                    >
                        <CollapsibleTrigger className="flex justify-between items-center w-full p-3">
                            <span className="text-gray-500">#用户提示词</span>
                            <div className="flex items-center">
                                <span className="mr-2 text-gray-500">
                                    {userPromptOpen ? "收起" : "展开"}
                                </span>
                                {userPromptOpen ?
                                    <ChevronUpIcon className="h-4 w-4" /> :
                                    <ChevronDownIcon className="h-4 w-4" />
                                }
                            </div>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="p-0">
                            <MDXEditor
                                profiles={profiles}
                                content={userPrompt}
                                onChange={setUserPrompt}
                                isEdit={true}
                            >

                            </MDXEditor>
                        </CollapsibleContent>
                    </Collapsible>

                    {/* Model Selection and Temperature Setting */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="mb-1 text-sm">选择模型：</div>
                            <ModelList value={model} onChange={setModel} />
                        </div>

                        <div>
                            <div className="mb-1 text-sm">设定温度：</div>
                            <div className="flex items-center space-x-2">
                                <Input
                                    type="text"
                                    value={temperature}
                                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                                    // step="0.1"
                                    // min="0"
                                    // max="1"
                                    className="w-full"
                                />
                                <Button variant="outline" size="icon" disabled={temperature <= 0} className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        if (temperature <= 0) {
                                            setTemperature(0);
                                            return;
                                        }
                                        setTemperature(Number((temperature - 0.1).toFixed(1)))
                                    }}
                                >
                                    <MinusIcon className="h-4 w-4" />
                                </Button>
                                <Button variant="outline" size="icon" disabled={temperature >= 1} className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        if (temperature >= 1) {
                                            setTemperature(1)
                                            return;
                                        }
                                        setTemperature(Number((temperature + 0.1).toFixed(1)))
                                    }}
                                >
                                    <PlusIcon className="h-4 w-4" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0">
                                    <TrashIcon className="h-4 w-4" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0">
                                    <ClipboardDocumentIcon className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>

                    {/* Occurrence Variables and Input Variable Values */}
                    <div>
                        {
                            profiles.map((item) => {
                                return (
                                    <div key={item} className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="mb-1 text-sm">出现变量：</div>
                                            <Input placeholder={item} />
                                        </div>
                                        <div>
                                            <div className="mb-1 text-sm">输入变量值：</div>
                                            <Input />
                                        </div>
                                    </div>
                                )
                            })
                        }
                    </div>



                    {/* Number of Columns and Maximum Number of Rows */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="mb-1 text-sm">列数（一个模型测几遍）：</div>
                            <div className="flex items-center space-x-2">
                                <Input
                                    type="text"
                                    value={rowCount}
                                    onChange={(e) => setRowCount(parseInt(e.target.value))}
                                    className="w-full"
                                />
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        if (rowCount <= 1) {
                                            setRowCount(1)
                                            return;
                                        }
                                        setRowCount(rowCount - 1)
                                    }}
                                >
                                    <MinusIcon className="h-4 w-4" />
                                </Button>
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
                                    onClick={() => {
                                        setRowCount(rowCount + 1)
                                    }}
                                >
                                    <PlusIcon className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>

                        <div>
                            <div className="mb-1 text-sm">最大行数：</div>
                            <Input type="number" placeholder="300" />
                        </div>
                    </div>

                    {/* Start Debugging Button */}
                    <div className="mt-6 flex justify-center">
                        <Button className="bg-purple-600 hover:bg-purple-700 text-white w-full py-6">
                            开始调试
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default AIModelDialog;
