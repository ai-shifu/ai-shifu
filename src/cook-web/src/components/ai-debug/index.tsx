import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
import MDXEditor from '@/components/md-editor';


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
        // 从当前块向上搜索，直到找到第一个systemprompt块
        const index = blocks.findIndex((item) => item.properties.block_id === blockId);
        for (let i = index - 1; i >= 0; i--) {
            if (blocks[i].properties.block_content.type === 'systemprompt') {
                setSystemPrompt(blocks[i].properties.block_content.properties.prompt);
                break;
            }
        }
    }
    useEffect(() => {
        init();
    }, [])
    return (
        <Dialog open={open} onOpenChange={onOpenChange} modal={true}>
            <DialogContent className="flex flex-col sm:max-w-[600px] max-h-[90vh] overflow-y-auto text-sm">
                <div className="absolute right-4 top-4 cursor-pointer">
                    <XMarkIcon className="h-4 w-4" onClick={() => onOpenChange(false)} />
                </div>
                <DialogHeader className="text-center">
                    <DialogTitle className="text-xl font-bold">调试AI模版</DialogTitle>
                </DialogHeader>
                <div className=" flex-1 space-y-4 overflow-auto px-2">
                    {/* 剧本信息 */}
                    {/* <div className="text-sm">
                        <span className="font-medium">剧本：</span>跟AI学编程&gt;&gt; 01-了解AI编程这回事&gt;&gt;打招呼
                    </div> */}

                    {/* AI模块内容 */}
                    <div className="text-sm font-medium">AI模块内容：</div>

                    {/* 系统提示词 */}
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
                        <CollapsibleContent className="p-3">
                            {/* 系统提示词内容 */}
                            <MDXEditor
                                className="markdown text-sm text-gray-700" value={systemPrompt}
                                onChange={setSystemPrompt}
                            >

                            </MDXEditor>

                        </CollapsibleContent>
                    </Collapsible>

                    {/* 用户提示词 */}
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
                        <CollapsibleContent className="p-3">
                            <MDXEditor
                                className="markdown text-sm text-gray-700" value={userPrompt}
                                onChange={setUserPrompt}
                            >

                            </MDXEditor>
                        </CollapsibleContent>
                    </Collapsible>

                    {/* 选择模型和温度设置 */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="mb-1 text-sm">选择模型：</div>
                            <Select value={model} defaultValue="GPT-4o-2024-5-13" onValueChange={setModel}>
                                <SelectTrigger className="w-full">
                                    <SelectValue placeholder="选择模型" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="GPT-4o-2024-5-13">GPT-4o-2024-5-13</SelectItem>
                                    <SelectItem value="GPT-4">GPT-4</SelectItem>
                                    <SelectItem value="GPT-3.5">GPT-3.5</SelectItem>
                                </SelectContent>
                            </Select>
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
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
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
                                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0"
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

                    {/* 出现变量和输入变量值 */}
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



                    {/* 列数和最大行数 */}
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

                    {/* 开始调试按钮 */}
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

// // 示例使用方式
// const App = () => {
//     const [dialogOpen, setDialogOpen] = useState(false);

//     return (
//         <div className="p-4">
//             <Button onClick={() => setDialogOpen(true)}>打开AI模版调试</Button>
//             <AIModelDialog open={dialogOpen} onOpenChange={setDialogOpen} />
//         </div>
//     );
// };

export default AIModelDialog;
