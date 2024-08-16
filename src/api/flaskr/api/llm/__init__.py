import decimal
from .ernie import *
from .glm import *
import openai
from flask import Flask
from langfuse.client import StatefulSpanClient
from langfuse.model import ModelUsage

from openai.types.chat import ChatCompletionStreamOptionsParam
from openai.types.chat.completion_create_params import ResponseFormat


from flaskr.common.config import get_config

client = openai.Client(api_key=get_config("OPENAI_API_KEY"),base_url=get_config("OPENAI_BASE_URL"))

try:
    OPENAI_MODELS = [i.id for i in client.models.list().data if i.id.startswith("gpt")]
except:
    OPENAI_MODELS = []
ERNIE_MODELS = get_erine_models(Flask(__name__))
GLM_MODELS = get_zhipu_models(Flask(__name__))



class LLMStreamaUsage:
    def __init__(self,prompt_tokens,completion_tokens,total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens=completion_tokens
        self.total_tokens=total_tokens
class LLMStreamResponse:
    def __init__(self,id,is_end,is_truncated,result,finish_reason,usage):
        self.id = id
    
        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.finish_reason = finish_reason
        self.usage = LLMStreamaUsage(**usage) if usage else None


def invoke_llm(app:Flask,span:StatefulSpanClient,model:str,message:str,system:str=None,json:bool=False,**kwargs)->Generator[LLMStreamResponse,None,None]:
    app.logger.info(f"invoke_llm [{model}] {message} ,system:{system} ,json:{json} ,kwargs:{kwargs}")
    kwargs.update({"stream":True})
    model = model.strip() 

    generation_input = []
    if system:
        generation_input.append({"role": "system", "content": system}) 
    generation_input.append({"role": "user", "content": message})
    generation = span.generation( model=model,input=generation_input) 
    response_text = ""
    usage = None
    if model in OPENAI_MODELS or model.startswith("gpt"):
        messages = []
        if system:
            messages.append({"content":system,"role":"system"})
        messages.append({"content":message,"role":"user"})
        if json:
            kwargs["response_format"] = ResponseFormat(type="json_object")
        kwargs["temperature"]=float(kwargs.get("temperature",0.8))
        kwargs["stream_options"]=ChatCompletionStreamOptionsParam(include_usage=True)
        response = client.chat.completions.create(model=model,messages=messages, **kwargs)
        for res in response:
            if len(res.choices) and  res.choices[0].delta.content:
                response_text += res.choices[0].delta.content
                yield LLMStreamResponse(res.id,
                                    True if res.choices[0].finish_reason else False,
                                    False,res.choices[0].delta.content,
                                    res.choices[0].finish_reason,None)
            if res.usage:
                usage = ModelUsage(unit="TOKENS", input=res.usage.prompt_tokens,output=res.usage.completion_tokens,total=res.usage.total_tokens)
           
    elif model in ERNIE_MODELS:
        if system:
            kwargs.update({"system":system}) 
        if json:
            kwargs["response_format"]="json_object"
        if kwargs.get("temperature",None) is  not None:
            kwargs["temperature"]=str(kwargs["temperature"])
        response = get_ernie_response(app,model, message,**kwargs)
        for res in response:
            response_text += res.result
            if res.usage:
                usage = ModelUsage(unit="TOKENS", input=res.usage.prompt_tokens,output=res.usage.completion_tokens,total=res.usage.total_tokens)
            yield LLMStreamResponse(res.id,res.is_end,res.is_truncated,res.result,res.finish_reason,res.usage.__dict__)
    elif model.lower() in GLM_MODELS:
        if kwargs.get("temperature",None) is  not None:
            kwargs["temperature"]=str(kwargs["temperature"])
        messages = []
        if system:
            messages.append({"content":system,"role":"system"})
        messages.append({"content":message,"role":"user"})
        response = invoke_glm(app,model.lower(),messages,**kwargs)
        for res in response:
            response_text += res.choices[0].delta.content
            if res.usage:
                usage = ModelUsage(unit="TOKENS", input=res.usage.prompt_tokens,output=res.usage.completion_tokens,total=res.usage.total_tokens)
            yield LLMStreamResponse(res.id,
                                    True if res.choices[0].finish_reason else False,
                                    False,res.choices[0].delta.content,
                                    res.choices[0].finish_reason,None)   
    else:
        app.logger.error(f"model {model} not found,use ERNIE-4.0-8K-Preview-0518")
        if system:
            kwargs.update({"system":system}) 
        if json:
            kwargs["response_format"]="json_object"
        if kwargs.get("temperature",None) is  not None:
            kwargs["temperature"]=str(kwargs["temperature"])
        response = get_ernie_response(app,"ERNIE-4.0-8K-Preview-0518", message,**kwargs)
        for res in response:
            response_text += res.result
            if res.usage:
                usage = ModelUsage(unit="TOKENS", input=res.usage.prompt_tokens,output=res.usage.completion_tokens,total=res.usage.total_tokens)
            yield LLMStreamResponse(res.id,res.is_end,res.is_truncated,res.result,res.finish_reason,res.usage.__dict__)

         
    app.logger.info(f"invoke_llm response: {response_text} ")
    app.logger.info(f"invoke_llm usage: "+usage.__str__())
    generation.end(input=generation_input, output=response_text,usage=usage,metadata=kwargs)        
    span.end(output=response_text) 


def get_current_models(app:Flask)->list[str]:
    app.logger.info([i.id for i in client.models.list().data])
    return OPENAI_MODELS+ERNIE_MODELS+GLM_MODELS