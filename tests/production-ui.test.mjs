import test from 'node:test';
import assert from 'node:assert/strict';

const ui = await import('../wholeboard/web/production.mjs').catch(() => ({}));

test('an incomplete estimate never displays an unknown total as free', () => {
  assert.equal(typeof ui.estimateSummary, 'function', 'Production estimate presentation is not implemented');
  const value = ui.estimateSummary({complete:false,total:null,known_total:12.5,currency:'USD',unknowns:['MCU price missing']});
  assert.equal(value.complete, false);
  assert.equal(value.total, '待补报价');
  assert.match(value.known, /12\.50/);
  assert.equal(ui.money(null), '—');
  assert.equal(ui.money(0), '$0.00');
});

test('a frozen package includes only selected files and requires version attestation', () => {
  assert.equal(typeof ui.buildPackagePayload, 'function', 'Production package validation is not implemented');
  const input={base_version:3,quantity:5,scope:'pcba',files_match_design:true,test_plan:'Power up with current limit',files:[{path:'rev1/fab/main.zip',role:'gerbers',selected:true},{path:'notes.txt',role:'other',selected:false}]};
  assert.deepEqual(ui.buildPackagePayload(input).files,[{path:'rev1/fab/main.zip',role:'gerbers'}]);
  assert.throws(()=>ui.buildPackagePayload({...input,files_match_design:false}),/核对/);
  assert.throws(()=>ui.buildPackagePayload({...input,quantity:1.5}),/整数/);
});

test('device estimates retain mechanical scope instead of pricing just an assembled board', () => {
  assert.equal(typeof ui.buildEstimatePayload,'function','Production estimate request validation is not implemented');
  assert.deepEqual(ui.buildEstimatePayload({base_version:3,quantity:'5',scope:'device',shipping_country:'cn',use_ai:true}),{base_version:3,quantity:5,scope:'device',assembly:true,shipping_country:'CN',use_ai:true});
  assert.equal(ui.buildEstimatePayload({base_version:3,quantity:5,scope:'pcb',shipping_country:'US',use_ai:false}).assembly,false);
  assert.throws(()=>ui.buildEstimatePayload({base_version:3,quantity:5,scope:'pcb',shipping_country:'USA'}),/国家/);
});

test('supplier quote payload validates amounts and preserves the exact RFQ revision', () => {
  assert.equal(typeof ui.buildQuotePayload, 'function', 'Supplier quote validation is not implemented');
  const input={base_revision:8,decision:'quote',supplier_name:'PCB team',contact_name:'Li',reference:'Q-17',currency:'USD',line_items:[{item:'PCB',amount:'12.50'},{item:'Assembly',amount:'5'}],lead_time_days:'7',valid_until:'2099-01-01',notes:''};
  const value=ui.buildQuotePayload(input);
  assert.equal(value.base_revision,8);
  assert.deepEqual(value.line_items,[{item:'PCB',amount:12.5},{item:'Assembly',amount:5}]);
  assert.throws(()=>ui.buildQuotePayload({...input,line_items:[{item:'PCB',amount:'NaN'}]}),/金额/);
  assert.throws(()=>ui.buildQuotePayload({...input,line_items:[{item:'PCB',amount:-1}]}),/金额/);
  assert.throws(()=>ui.buildQuotePayload({...input,valid_until:'2000-01-01'}),/有效期/);
  assert.throws(()=>ui.buildQuotePayload({...input,currency:'xx'}),/币种/);
  assert.throws(()=>ui.buildQuotePayload({...input,lead_time_days:731}),/730/);
});

test('production stages cannot be offered before a quotation is accepted or move backwards', () => {
  assert.equal(typeof ui.allowedProgress, 'function', 'Production progress validation is not implemented');
  assert.deepEqual(ui.allowedProgress({status:'quoted',accepted_quote_id:null}),[]);
  const options=ui.allowedProgress({status:'testing',accepted_quote_id:'q1'});
  assert.ok(options.includes('shipped'));
  assert.ok(options.includes('on_hold'));
  assert.ok(!options.includes('production'));
  const resumed=ui.allowedProgress({status:'on_hold',resume_status:'testing',accepted_quote_id:'q1'});
  assert.ok(!resumed.includes('production'));
  assert.ok(resumed.includes('testing'));
  assert.deepEqual(ui.allowedProgress({status:'delivered',accepted_quote_id:'q1'}),[]);
});

test('an older quote and an estimate for another batch are never offered for acceptance', () => {
  assert.equal(typeof ui.canAcceptQuote, 'function', 'Current quote selection is not implemented');
  const old={id:'q1',valid_until:'2099-01-01'},current={id:'q2',valid_until:'2099-01-01'},rfq={status:'quoted',quotes:[old,current],accepted_quote_id:null};
  assert.equal(ui.canAcceptQuote(rfq,old),false);
  assert.equal(ui.canAcceptQuote(rfq,current),true);
  assert.equal(ui.canAcceptQuote({...rfq,accepted_quote_id:'q2'},current),false);
  assert.equal(typeof ui.estimateForPackage,'function');
  assert.equal(ui.estimateForPackage([{id:'wrong-batch',spec_sha256:'a',quantity:50},{id:'right',spec_sha256:'a',quantity:5}],{spec_sha256:'a',quantity:5}).id,'right');
  assert.equal(ui.estimateForPackage([{id:'wrong-design',spec_sha256:'b',quantity:5}],{spec_sha256:'a',quantity:5}),undefined);
  assert.equal(ui.estimateForPackage([{id:'pcb-only',spec_sha256:'a',quantity:5,scope:'pcb'},{id:'whole-device',spec_sha256:'a',quantity:5,scope:'device'}],{spec_sha256:'a',quantity:5,scope:'device'}).id,'whole-device');
  assert.equal(ui.estimateForPackage([{id:'pcb-only',spec_sha256:'a',quantity:5,scope:'pcb'}],{spec_sha256:'a',quantity:5,scope:'pcba'}),undefined);
});

test('a stale mutation reports its conflict and never silently retries the supplier action', async () => {
  assert.equal(typeof ui.createClient, 'function', 'Production API client is not implemented');
  let calls=0;
  const client=ui.createClient(async (url,options)=>{
    calls++;
    assert.equal(url,'/api/projects/p/production/rfqs/r/accept');
    assert.equal(options.credentials,'same-origin');
    assert.equal(options.method,'POST');
    assert.equal(JSON.parse(options.body).base_revision,2);
    return {ok:false,status:409,json:async()=>({detail:'The RFQ changed. Reload before accepting.'})};
  });
  await assert.rejects(client('/api/projects/p/production/rfqs/r/accept',{method:'POST',body:{base_revision:2,quote_id:'q1'}}),e=>e.status===409&&e.message.includes('RFQ changed'));
  assert.equal(calls,1);
});

test('supplier-rendered text cannot introduce markup or script URLs', () => {
  assert.equal(typeof ui.escapeHTML, 'function', 'Production text escaping is not implemented');
  assert.equal(ui.escapeHTML('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(ui.safeHref('javascript:alert(1)'), '#');
  assert.equal(ui.safeHref('/\\evil.example'), '#');
  assert.equal(ui.safeHref('/api/production/supplier/t/package'), '/api/production/supplier/t/package');
});
