import {icon,esc} from './workbench-icons.mjs';
import {buildFileTree,fileRows,isDocument,isAsset,imageFile} from './workbench-files-model.mjs';

export class FilesTreeUI{
 constructor({host,data,pid,state={},select,refresh,toggle,editable}){
  Object.assign(this,{host,data,pid,state,select,refresh,toggle,editable});this.tree=buildFileTree(data.files,{native:data.native});this.selected=null;
  this.expanded=state.expanded||new Set(['','docs','native','history','firmware']);if(data.native?.folder)this.expanded.add(data.native.folder);this.scope=state.scope||'documents';this.query=state.query||'';
  try{if(!state.expanded){const stored=JSON.parse(localStorage.getItem('wb-file-tree:'+pid)||'null');if(stored?.expanded)this.expanded=new Set(stored.expanded);}}catch{}
  host.innerHTML=`<div class="file-tree-heading"><span>${icon('list')}Files</span><button class="icon-button" id="closeFileTree" aria-label="Close file browser">×</button></div><div class="file-documents-heading"><h3>Documents</h3><button class="asset-text-button" id="newTextFile" ${!editable?'disabled':''}>${icon('plus')}New</button></div><p class="file-documents-description" id="fileDocumentsDescription">Documents are markdown text files which describe project goals, capture details, or even simulation outputs.</p><div class="file-catalog-tools"><div class="drawer-search">${icon('search')}<input id="fileSearch" type="search" aria-label="Search project files" placeholder="Search files"><button class="icon-button" id="expandFileFolders" aria-label="Expand all folders" title="Expand all folders">${icon('chevronDown')}</button><button class="icon-button" id="collapseFileFolders" aria-label="Collapse all folders" title="Collapse all folders">${icon('chevronRight')}</button></div><div class="file-catalog-scope"><select id="fileCatalogScope" aria-label="File scope"><option value="documents">Documents</option><option value="assets">Assets</option><option value="all">All files</option><option value="current">Current generation</option><option value="saved">Saved outputs &amp; history</option></select><button class="icon-button" id="refreshProjectFiles" aria-label="Refresh project files" title="Refresh project files">${icon('rotate')}</button></div></div><div id="fileTreeList" class="file-tree-list" role="tree" aria-label="Project files"></div><div id="fileAssetSection" class="file-assets-section"><h3>Assets</h3><div id="fileAssetList"></div></div><div id="fileCatalogStatus" class="file-catalog-status" role="status"></div>`;
  host.querySelector('#fileSearch').value=this.query;host.querySelector('#fileCatalogScope').value=this.scope;
  host.querySelector('#closeFileTree').onclick=toggle;host.querySelector('#refreshProjectFiles').onclick=refresh;
  host.querySelector('#fileSearch').oninput=event=>{this.query=event.target.value;this.remember();this.render();};
  host.querySelector('#fileCatalogScope').onchange=event=>{this.scope=event.target.value;this.remember();this.render();};
  host.querySelector('#expandFileFolders').onclick=()=>{this.expanded=new Set([...this.tree.nodes.values()].filter(n=>n.kind==='folder').map(n=>n.path));this.remember();this.render();};
  host.querySelector('#collapseFileFolders').onclick=()=>{this.expanded=new Set(['']);this.remember();this.render();};
  const list=host.querySelector('#fileTreeList');list.dataset.projectId=pid;
  list.onclick=event=>{const row=event.target.closest('[data-file-node]');if(!row)return;this.activate(row.dataset.fileNode);};
  list.onkeydown=event=>{
   const row=event.target.closest('[data-file-node]');if(!row)return;const node=this.tree.nodes.get(row.dataset.fileNode),index=this.rows.findIndex(n=>n.id===node.id);let target;
   if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();event.stopPropagation();target=this.rows[event.key==='Home'?0:event.key==='End'?this.rows.length-1:Math.max(0,Math.min(this.rows.length-1,index+(event.key==='ArrowDown'?1:-1)))]?.id;}
   if(event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();if(node.kind==='folder'&&!this.expanded.has(node.path)){this.expanded.add(node.path);this.remember();this.render();}else target=node.children[0];}
   if(event.key==='ArrowLeft'){event.preventDefault();event.stopPropagation();if(node.kind==='folder'&&this.expanded.has(node.path)){this.expanded.delete(node.path);this.remember();this.render();}else target=node.parent;}
   if(['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();this.activate(node.id);}
   if(target)list.querySelector(`[data-file-node="${CSS.escape(target)}"]`)?.focus({preventScroll:true});
  };
  host.querySelector('#fileAssetList').onclick=event=>{const button=event.target.closest('[data-asset-path]');if(button)this.select(button.dataset.assetPath);};
  this.render();
 }
 remember(){Object.assign(this.state,{expanded:this.expanded,scope:this.scope,query:this.query});try{localStorage.setItem('wb-file-tree:'+this.pid,JSON.stringify({expanded:[...this.expanded]}));}catch{}}
 activate(id){const node=this.tree.nodes.get(id);if(!node)return;if(node.kind==='folder'){this.expanded.has(node.path)?this.expanded.delete(node.path):this.expanded.add(node.path);this.remember();this.render();}else this.select(node.path);}
 setSelected(path){
  this.selected=path;let node=this.tree.nodes.get('file:'+path);while(node?.parent){node=this.tree.nodes.get(node.parent);this.expanded.add(node.path);}
  if(path&&!fileRows(this.tree,{expanded:this.expanded,query:this.query,scope:this.scope}).some(n=>n.path===path)){const file=this.tree.nodes.get('file:'+path)?.file;this.scope=file&&isDocument(file)?'documents':file&&isAsset(file)?'assets':'all';this.query='';this.host.querySelector('#fileSearch').value='';this.host.querySelector('#fileCatalogScope').value=this.scope;}
  this.remember();this.render();
 }
 reveal(){if(!this.selected)return;this.scope='all';this.query='';this.host.querySelector('#fileSearch').value='';this.host.querySelector('#fileCatalogScope').value='all';this.setSelected(this.selected);this.host.querySelector(`[data-file-node="${CSS.escape('file:'+this.selected)}"]`)?.scrollIntoView({block:'nearest'});}
 render(){
  const list=this.host.querySelector('#fileTreeList'),focused=document.activeElement?.closest('[data-file-node]')?.dataset.fileNode,scroll=list.scrollTop;
  this.rows=fileRows(this.tree,{expanded:this.expanded,query:this.query,scope:this.scope});const stamp=JSON.stringify(this.rows.map(n=>[n.id,n.expanded]));
  if(stamp!==this.stamp){this.stamp=stamp;list.innerHTML=this.rows.map(node=>node.kind==='folder'?`<button class="file-folder-entry" role="treeitem" aria-level="${node.depth+1}" aria-expanded="${node.expanded}" data-file-node="${esc(node.id)}" data-folder-path="${esc(node.path)}" style="--file-depth:${node.depth}" title="${esc(node.path)}">${icon(node.expanded?'chevronDown':'chevronRight')}${icon('folder')}<span>${esc(node.name)}</span>${node.badge?`<small title="${esc(node.badge)}">${esc(node.badge==='Current generation'?'Current':node.badge)}</small>`:''}</button>`:`<button class="file-entry${node.path===this.selected?' active':''}" role="treeitem" aria-level="${node.depth+1}" aria-selected="${node.path===this.selected}" data-file-node="${esc(node.id)}" data-file-path="${esc(node.path)}" title="${esc(node.path)}" style="--file-depth:${node.depth}">${icon('file')}<span>${esc(node.name)}</span>${node.badge?`<small title="${esc(node.badge)}">${esc(node.badge.startsWith('Current ')?'Current':node.badge==='Prior geometry'?'Prior':'')}</small>`:''}</button>`).join('')||'<p class="file-no-results">No matching files.</p>';
   list.scrollTop=scroll;if(focused)list.querySelector(`[data-file-node="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
  }else for(const element of list.querySelectorAll('[data-file-path]')){const selected=element.dataset.filePath===this.selected;element.classList.toggle('active',selected);element.setAttribute('aria-selected',String(selected));}
  const documents=this.data.files.filter(isDocument),assets=this.data.files.filter(isAsset),showAssets=this.scope==='documents'&&!this.query;
  this.host.classList.toggle('documents-mode',showAssets);
  this.host.querySelector('#fileDocumentsDescription').hidden=this.scope!=='documents'||documents.length>0;this.host.querySelector('.file-documents-heading').hidden=this.scope!=='documents';
  this.host.querySelector('#fileAssetSection').hidden=!showAssets;
  const gallery=this.host.querySelector('#fileAssetList');if(showAssets){const signature=JSON.stringify(assets.map(f=>[f.path,f.url]));if(signature!==this.assetStamp){this.assetStamp=signature;gallery.innerHTML=assets.map(f=>`<button class="file-asset-card" data-asset-path="${esc(f.path)}" title="${esc(f.path)}">${imageFile(f)?`<img src="${esc(f.url)}" alt="" loading="lazy">`:icon('file')}<span>${esc(f.name)}</span></button>`).join('')||'<p class="file-no-results">No assets yet.</p>';}}
  const outside=this.selected&&!this.rows.some(r=>r.path===this.selected),status=this.host.querySelector('#fileCatalogStatus');status.textContent=`${this.data.files.length} files${outside?' · Selected file outside filter':''}${this.data.scan_errors_count?' · Some folders could not be read':''}`;
 }
}
