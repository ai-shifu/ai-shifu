import request from '../Service/Request';



export const GetAllDocuments = async()=>{
    return request({
        url:'/api/document/all',
        method:'get'
    });
}

export const GetDocumentById = async(id)=>{
    return request({
        url:'/api/document/detail?id='+id,
        method:'get'
    });
}
