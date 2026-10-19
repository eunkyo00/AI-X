import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiWorkspace, BrowserLibrary, normalizeResponse, normalizeFile, validateFile, validateBaseUrl } from '../web/workspace-service.mjs';

test('null metadata remains unknown and no evidence or task grouping is invented',()=>{
  const file=normalizeFile({file_id:'x',name:'한글 코드.py',role:null,modified:null,evidence:null});
  assert.equal(file.role,'알 수 없음');assert.equal(file.modified,'');assert.equal(file.task,null);assert.deepEqual(file.evidence,[]);assert.equal(file.type,'code');
  const response=normalizeResponse({files:[{file_id:'x',name:'x.csv'}],relations:[{from:'x',to:'missing',certainty:'confirmed'}]});
  assert.deepEqual(response.relations,[]);
  assert.throws(()=>normalizeResponse({files:[{file_id:'x',name:'a.txt'},{file_id:'x',name:'b.txt'}]}),/중복/);
  assert.throws(()=>normalizeResponse({files:[{name:'no-id.txt'}]}),/ID/);
});

test('file admission and API URLs reject unsupported inputs',()=>{
  assert.equal(validateFile({name:'한글 공백.R',size:10}),null);
  assert.match(validateFile({name:'test.exe',size:10}),/지원/);
  assert.match(validateFile({name:'test.pdf',size:26*1024*1024}),/25MB/);
  assert.equal(validateBaseUrl('http://127.0.0.1:8000/api/'),'http://127.0.0.1:8000/api');
  for(const value of ['javascript:alert(1)','file:///tmp','https://user:pass@example.com','https://example.com/?token=x'])assert.throws(()=>validateBaseUrl(value));
});

test('API adapter preserves server order and injects server-provided related catalog',async()=>{
  let request;
  const api=new ApiWorkspace('http://127.0.0.1:8000/api',async(url,options)=>{
    request={url,options};
    return Response.json({files:[{file_id:'b',name:'code.py',rank:2,task_id:'t',task_name:'서버 작업'},{file_id:'a',name:'input.csv',rank:1}],catalog:[{file_id:'c',name:'out.csv'}],relations:[{source_file_id:'b',target_file_id:'c',label:'저장 경로',certainty:'confirmed'}]});
  });
  const response=await api.search('서버 질의');
  assert.deepEqual(response.files.map(file=>file.id),['b','a']);
  assert.deepEqual(response.files.map(file=>file.rank),[1,2]);
  assert.equal(response.catalog.length,3);assert.equal(response.taskNames.t,'서버 작업');assert.equal(response.relations[0].to,'c');
  assert.equal(response.files[0].apiBase,api.base);assert.equal(JSON.parse(request.options.body).query,'서버 질의');
  assert.equal(request.options.credentials,'omit');assert.equal(request.options.redirect,'error');
});

test('health rejects incompatible contracts and HTTP failures; no demo fallback',async()=>{
  const api=new ApiWorkspace('http://127.0.0.1:8000/api',async()=>Response.json({status:'ok',contract_version:'other'}));
  await assert.rejects(api.health(),/계약/);
  api.fetcher=async()=>new Response('',{status:404});
  await assert.rejects(api.list(),/경로/);
});

test('file paths stay behind encoded IDs and file upload uses FormData',async()=>{
  const calls=[];
  const api=new ApiWorkspace('http://127.0.0.1:8000/api',async(url,options)=>{
    calls.push({url,options});
    if(url.endsWith('/content'))return new Response('print("do not execute")');
    return Response.json({file:{file_id:'new',name:'한글 파일.py',index_status:'processing'},job_id:'job/1'});
  });
  const uploaded=await api.add(new File(['print("safe")'],'한글 파일.py'));
  assert.equal(uploaded.file.indexStatus,'processing');assert.equal(uploaded.jobId,'job/1');assert.ok(calls[0].options.body instanceof FormData);
  await api.blob('../../test');assert.ok(calls[1].url.endsWith('/files/..%2F..%2Ftest/content'));
});

test('API deadline aborts fetch and browser storage absence is a clear failure',async()=>{
  const api=new ApiWorkspace('http://127.0.0.1:8000/api',(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')))));
  await assert.rejects(api.request('/health',{timeoutMs:5}),/시간/);
  await assert.rejects(new BrowserLibrary(null).list(),/보관/);
});

test('default browser fetch keeps its global receiver',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=function(){
    assert.equal(this,globalThis);
    return Promise.resolve(Response.json({status:'ok',contract_version:'gui-v1',index_ready:false}));
  };
  try {
    const result=await new ApiWorkspace('http://127.0.0.1:8000/api').health();
    assert.equal(result.index_ready,false);
  }finally{globalThis.fetch=original;}
});
