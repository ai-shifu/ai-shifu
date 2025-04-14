import { fail } from "@/hooks/use-toast";

const getCurrentModelConfig = () => {
    return {
        apiKey: '',
        baseUrl: ''
    };
}


export class ErrorWithCode extends Error {
    code: number;
    constructor(message: string, code: number) {
        super(message);
        this.code = code;
    }
}

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

export function mergeToolCalls(toToolCalls: any[], fromToolCalls: any[]) {
    if (fromToolCalls.length <= 0) {
        return toToolCalls;
    }
    fromToolCalls.forEach(fromToolCall => {
        const matchingIndex = toToolCalls.findIndex(toToolCall => toToolCall.index === fromToolCall.index);

        if (matchingIndex !== -1) {
            // 合并已存在的 toolCall
            const toToolCall = toToolCalls[matchingIndex];
            // 合并 function 对象的属性，例如 arguments 和 name
            Object.keys(fromToolCall.function).forEach(key => {
                toToolCall.function[key] += fromToolCall.function[key];
            });
            // 如果 fromToolCall 中有其他属性，也合并到 toToolCall 中
            Object.keys(fromToolCall).forEach(key => {
                if (key !== 'function') {
                    toToolCall[key] = fromToolCall[key];
                }
            });
        } else {
            // 如果不存在，则将整个 fromToolCall 添加到 toToolCalls 中
            toToolCalls.push(fromToolCall);
        }
    });

    return toToolCalls;
}

export const chat = async (body: any) => {

    const { apiKey, baseUrl } = await getCurrentModelConfig();
    const key = apiKey;
    const response = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${key}`
        },
        body: JSON.stringify(body)
    });
    if (!response.ok) {
        fail(`Request failed with status ${response.status} ${response.statusText}`);
        throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
    }
    const result = await response.json();
    // console.log(result)
    return result;
};

export const models = async (baseUrl: string, apiKey: string) => {
    const key = apiKey;
    const response = await fetch(`${baseUrl}/models`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${key}`
        }
    });
    // check status
    if (!response.ok) {
        fail(`Request failed with status ${response.status} ${response.statusText}`);
        throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
    }
    const result = await response.json();
    // console.log(result)
    return result;
};

export const chatStream = async (body: any, callback: any) => {
    const { apiKey, baseUrl } = await getCurrentModelConfig();
    const key = apiKey;
    try {
        const controller = new AbortController();
        (window as any).abort = () => {
            controller.abort();
        }
        const response = await fetch(`${baseUrl}/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${key}`
            },
            body: JSON.stringify(body),
            signal: controller.signal,
        });
        // const result = await response.json();
        if (!response.ok) {
            fail(`Request failed with status ${response.status} ${response.statusText}`);
            throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
        }

        const data = response.body;
        if (!data) {
            fail(`Request failed with status ${response.status} ${response.statusText}`);
            throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
        }
        const reader = data.getReader();
        let done = false;
        const stop = () => {
            done = true;
            controller.abort();
        };
        const res: any = { content: '', reasoning_content: '', delta: { content: '', reasoning_content: '', }, tool_calls: [] };
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
            // lines.push(json)
            if (data.choices && data.choices.length > 0) {
                const choice = data.choices[0];
                const content = choice.delta?.content;
                const reasoning_content = choice.delta?.reasoning_content;
                const toolCalls = choice.delta?.tool_calls;

                if (reasoning_content !== undefined && reasoning_content != null) {
                    res.reasoning_content += reasoning_content;
                    res.delta.reasoning_content = reasoning_content;
                } else {
                    res.delta.reasoning_content = "";
                }

                if (content !== undefined && content != null) {
                    res.content += content;
                    res.delta.content = content;
                } else {
                    res.delta.content = "";
                }

                if (toolCalls != undefined) {
                    res.tool_calls = mergeToolCalls(res.tool_calls, toolCalls);
                }
            } else if (data.error) {
                fail(data.error.message);
                throw new Error(JSON.stringify(data.error, null, 2));
            }
            if (callback && res) {
                await callback(done, res, () => {
                    stop();
                });
            }
        }
        if (callback) {
            await callback(true, '', () => {
                stop();
            });
        }
        return res;
    } catch (error: any) {
        // 可以在这里处理异常，例如上报错误，显示错误提示等
        console.error('Request failed:', error);
        console.log(error.stack);
        throw error;
    }
};
export const embeddings = async (body: any) => {
    const { apiKey, baseUrl } = await getCurrentModelConfig();
    const key = apiKey;
    const response = await fetch(`${baseUrl}/embeddings`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${key}`
        },
        body: JSON.stringify(body)
    });
    if (!response.ok) {
        throw new ErrorWithCode(`Request failed with status ${response.status} ${response.statusText}`, response.status);
    } else {
        const result = await response.json();
        return result.data[0].embedding;
    }
};

export const generateImages = async (body: any) => {

    const { apiKey, baseUrl } = await getCurrentModelConfig();
    const key = apiKey;
    const response = await fetch(`${baseUrl}/images/generations`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${key}`
        },
        body: JSON.stringify(body)
    });
    const result = await response.json();
    // console.log(result)
    return result;
};
