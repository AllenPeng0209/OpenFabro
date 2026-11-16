import { marked } from './vendor/marked.mjs';
import DOMPurify from './vendor/purify.mjs';

const cache = new Map();
export function renderMarkdown(value,options={}) {
  const text=String(value||''),base=options.baseUrl?new URL(options.baseUrl,location.href).href:null,key=JSON.stringify([base,text]);
  if(cache.has(key))return cache.get(key);
  const html=DOMPurify.sanitize(marked.parse(text,{gfm:true,breaks:true}),{
    USE_PROFILES:{html:true},FORBID_TAGS:['iframe','object','embed','style','form','input','button','textarea','select','option'],FORBID_ATTR:['style','id','name'],ALLOW_DATA_ATTR:false,
  });
  const template=document.createElement('template');template.innerHTML=html;
  const headings=new Map(),counts=new Map();
  if(base)for(const [index,heading]of [...template.content.querySelectorAll('h1,h2,h3,h4,h5,h6')].entries()){
    const slug=(heading.textContent||'section').toLowerCase().trim().replace(/[^\p{L}\p{N}\s_-]/gu,'').replace(/\s+/g,'-')||'section',number=(counts.get(slug)||0)+1;counts.set(slug,number);const fragment=slug+(number>1?'-'+number:'');heading.id=`doc-heading-${index}-${fragment}`;headings.set(fragment,heading.id);
  }
  for(const a of template.content.querySelectorAll('a[href]')){
    const href=a.getAttribute('href');
    if(base&&href.startsWith('#')){let fragment;try{fragment=decodeURIComponent(href.slice(1)).toLowerCase();}catch{fragment=href.slice(1);}a.setAttribute('href','#'+(headings.get(fragment)||fragment));a.removeAttribute('target');continue;}
    if(base){try{a.href=new URL(href,base).href;}catch{a.removeAttribute('href');}}
    a.rel='noopener noreferrer';a.target='_blank';
  }
  for(const img of template.content.querySelectorAll('img[src]')){
    const raw=img.getAttribute('src');let src=raw;
    if(base){try{src=new URL(raw,base).href;img.src=src;}catch{img.remove();continue;}}
    try{const url=new URL(src,location.origin);if(url.origin!==location.origin&&!src.startsWith('data:image/')){
      const a=document.createElement('a');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';a.textContent=img.alt||'View image';img.replaceWith(a);
    }}catch{img.remove();}
  }
  const result=template.innerHTML;
  if(cache.size>100)cache.delete(cache.keys().next().value);cache.set(key,result);
  return result;
}
