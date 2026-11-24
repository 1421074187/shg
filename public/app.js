'use strict';
const $=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg';
let bootstrap, result, baselineMaps, busy=false, dirty=false, state={u:45,l:60,h:50};
const charts=[];
const fixed=v=>Number.isFinite(v)?v.toFixed(3):'无法判定';
const precise=v=>Number.isFinite(v)?(v!==0&&(Math.abs(v)<.001||Math.abs(v)>=1000)?v.toExponential(3):v.toFixed(4)):'无法判定';
const intensityTicks=[0,1,2,4,8];
const intensityScale=value=>Math.min(1,Math.log1p(value)/Math.log1p(intensityTicks.at(-1)));
function svg(tag,attrs={},text){const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;return el;}
function showStatus(text,kind=''){ $('status').textContent=text;$('status').className='status '+kind; }
function dirtySettings(){dirty=true;$('results').classList.add('stale');for(const id of ['upper','lower'])$(id).disabled=true;showStatus('参数已修改。点击“计算并更新厚度图”后生效；下方仍是上一次的结果。','dirty');}
function materialInputs(){
  for(const [side,title] of [['upper','上层 NbOCl₂'],['lower','下层 NbOCl₂']]){
    const block=document.createElement('section');block.className='material-section';
    const h=document.createElement('h3');h.textContent=title;block.append(h);
    const nGrid=document.createElement('div');nGrid.className='input-grid';
    for(const w of ['1064','532']){
      const caption=document.createElement('p');caption.className='group-label';caption.textContent=w==='1064'?'基频光 1064 nm：复折射率':'SHG 532 nm：复折射率';nGrid.append(caption);
      for(const axis of ['b','c'])addInput(nGrid,`${side}-n-${w}-${axis}`,`${axis} 轴`,bootstrap.defaults.n[w][axis]);
    }
    block.append(nGrid);
    const cGrid=document.createElement('div');cGrid.className='chi-grid';
    for(const c of ['bbb','bcc','cbc'])addInput(cGrid,`${side}-chi-${c}`,`非线性系数 χ${c}`,bootstrap.defaults.chi[c]);
    block.append(cGrid);$('materials').append(block);
  }
}
function addInput(parent,id,labelText,placeholder){const label=document.createElement('label');label.textContent=labelText;const input=document.createElement('input');input.id=id;input.type='text';input.placeholder=placeholder;input.autocomplete='off';input.spellcheck=false;input.addEventListener('input',dirtySettings);label.append(input);parent.append(label);}
function payload(){
  const p={h:Number($('spacer').value),angle:Number($('angle').value),input:$('input').value,linear_angle:Number($('linear-angle').value)};
  for(const side of ['upper','lower']){
    p[side]={n:{},chi:{}};
    for(const w of ['1064','532']){p[side].n[w]={};for(const a of ['b','c'])p[side].n[w][a]=$(`${side}-n-${w}-${a}`).value;}
    for(const c of ['bbb','bcc','cbc'])p[side].chi[c]=$(`${side}-chi-${c}`).value;
  }
  return p;
}
function statusForResult(){showStatus(result.mode==='baseline'?'默认参数 · 已完成的扫描结果。点击厚度图或拖动滑块选点。':'已按当前材料参数与角度重新计算。点击厚度图或拖动滑块选点。');}
async function withBaselineMaps(data){
  if(data.maps)return data;
  if(!baselineMaps){
    const response=await fetch('/data/baseline_maps.json');
    if(!response.ok)throw new Error('无法读取默认厚度扫描数据。');
    baselineMaps=await response.json();
  }
  if(data.baseline_sign===1)return {...data,maps:baselineMaps};
  const negate=value=>value===null?null:-value;
  const maps={...baselineMaps};
  for(const field of ['s2','s3','S2','S3'])maps[field]=baselineMaps[field].map(negate);
  const [s0,s1,s2]=baselineMaps.zero_stokes;
  maps.zero_stokes=[s0,s1,s2.map(negate)];
  return {...data,maps};
}
async function calculate(){
  if(busy)return;
  if(!$('settings').reportValidity())return;
  busy=true;$('apply').disabled=true;$('results').classList.add('stale');for(const id of ['upper','lower'])$(id).disabled=true;
  showStatus('正在计算完整结构及厚度邻域，请稍候…');
  const p=payload();
  const fingerprint=JSON.stringify(p);
  try{
    const headers={'Content-Type':'application/json'};
    if(bootstrap.token)headers['X-App-Token']=bootstrap.token;
    const response=await fetch('/api/calculate',{method:'POST',headers,body:JSON.stringify(p)});
    const data=await response.json().catch(()=>null);
    if(!response.ok||!data)throw new Error(data?.error||'计算失败。');
    result=await withBaselineMaps(data);state.h=p.h;
    $('mode').textContent=result.mode==='baseline'?'默认基线 · 条件预测':'自定义计算 · 条件预测';
    dirty=JSON.stringify(payload())!==fingerprint;
    $('results').classList.toggle('stale',dirty);render(true);
    if(dirty)dirtySettings();else statusForResult();
  }catch(error){dirty=true;showStatus(error.message+' 下方保留上一次结果。','error');}
  finally{busy=false;$('apply').disabled=false;for(const id of ['upper','lower'])$(id).disabled=dirty;}
}
function index(ui,li){const d=result.maps;return(d.hbn.indexOf(state.h)*d.upper.length+ui)*d.lower.length+li;}
function value(name,i){return result.maps[name][i];}
function color(value,kind){
  if(!Number.isFinite(value))return 'var(--line)';
  const x=kind==='intensity'?intensityScale(value):value;
  return `color-mix(in srgb, var(${x<0?'--blue':'--orange'}) ${Math.min(1,Math.abs(x))*100}%, var(--bg))`;
}
function makeChart(id,kind){const c={el:$(id),kind,width:0,cells:[],left:56,top:12};charts.push(c);c.el.addEventListener('click',e=>{if(dirty||busy)return;const rect=e.target.closest('[data-ui]');if(!rect)return;state.u=result.maps.upper[Number(rect.dataset.ui)];state.l=result.maps.lower[Number(rect.dataset.li)];render(false);});return c;}
function layout(c){
  if(!result)return;const width=Math.floor(c.el.parentElement.clientWidth);if(c.width===width&&c.cells.length)return;c.width=width;c.size=width-c.left-12;const height=c.top+c.size+58,d=result.maps,cell=c.size/d.upper.length;
  c.el.setAttribute('viewBox',`0 0 ${width} ${height}`);c.el.setAttribute('height',height);c.el.replaceChildren();c.cells=[];
  c.el.append(svg('title',{},c.kind==='intensity'?'统一参考下的反射 SHG 强度':'归一化圆偏度'));
  c.el.append(svg('desc',{},'横轴下层 NbOCl2 厚度，纵轴上层厚度，单位 nm。每格为一个扫描点；可以使用厚度滑块选点。'));
  for(let ui=0;ui<d.upper.length;ui++)for(let li=0;li<d.lower.length;li++){
    const mark=svg('rect',{x:c.left+li*cell,y:c.top+(d.upper.length-ui-1)*cell,width:cell+.05,height:cell+.05,'data-ui':ui,'data-li':li,class:'cell'});c.el.append(mark);c.cells.push({el:mark,ui,li});
  }
  for(const t of(width<350?[20,100,200]:[20,50,100,150,200])){
    const pos=(t-20)/5+.5,x=c.left+pos*cell,y=c.top+c.size-pos*cell;
    c.el.append(svg('text',{x,y:c.top+c.size+22,'text-anchor':'middle',class:'tick'},t));
    c.el.append(svg('text',{x:c.left-8,y,'text-anchor':'end','dominant-baseline':'middle',class:'tick'},t));
  }
  c.el.append(svg('text',{x:c.left+c.size/2,y:height-6,'text-anchor':'middle'},'下层 NbOCl₂ 厚度（nm）'));
  const cy=c.top+c.size/2;c.el.append(svg('text',{x:14,y:cy,transform:`rotate(-90 14 ${cy})`,'text-anchor':'middle'},'上层 NbOCl₂ 厚度（nm）'));
  c.rings=svg('g',{class:'rings'});c.el.append(c.rings);c.marker=svg('g',{class:'selection'});
  for(const [stroke,width] of [['var(--bg)',5],['var(--fg)',2]])for(const line of [{x1:-8,x2:8,y1:0,y2:0},{x1:0,x2:0,y1:-8,y2:8}])c.marker.append(svg('line',{...line,stroke,'stroke-width':width}));
  c.el.append(c.marker);paint(c);marker(c);
}
function paint(c){
  const d=result.maps,cell=c.size/d.upper.length;c.rings.replaceChildren();
  for(const entry of c.cells){const {el,ui,li}=entry,i=index(ui,li),v=value(c.kind==='intensity'?'Q':'s3',i);el.setAttribute('fill',color(v,c.kind));let title=el.firstElementChild;if(!title){title=svg('title');el.append(title);}title.textContent=`上 ${d.upper[ui]} / hBN ${state.h} / 下 ${d.lower[li]} nm；统一参考强度 ${fixed(value('Q',i))}；圆偏度 ${fixed(value('s3',i))}`;
    if(d.qualified[i])for(const [stroke,width] of [['var(--bg)',3],['var(--fg)',1.2]])c.rings.append(svg('circle',{cx:c.left+(li+.5)*cell,cy:c.top+(d.upper.length-ui-.5)*cell,r:Math.max(3,cell*.38),fill:'none',stroke,'stroke-width':width}));
  }
}
function marker(c){if(!c.marker)return;const d=result.maps,cell=c.size/d.upper.length;c.marker.setAttribute('transform',`translate(${c.left+(d.lower.indexOf(state.l)+.5)*cell},${c.top+(d.upper.length-d.upper.indexOf(state.u)-.5)*cell})`);}
function ellipse(i){
  const a=value('s1',i),b=value('s2',i),c=value('s3',i);if(![a,b,c].every(Number.isFinite)){$('polar-path').setAttribute('d','');return;}
  const psi=.5*Math.atan2(b,a),ratio=Math.tan(.5*Math.asin(Math.min(1,Math.abs(c)))),points=[];
  for(let j=0;j<=64;j++){const t=j*2*Math.PI/64,x=29*Math.cos(t),y=29*ratio*Math.sin(t);points.push(`${j?'L':'M'}${x*Math.cos(psi)-y*Math.sin(psi)},${-x*Math.sin(psi)-y*Math.cos(psi)}`);}
  $('polar-path').setAttribute('d',points.join(' ')+' Z');
}

function analyzerIntensity([s0,s1,s2],angle){
  return Math.max(0,(s0+s1*Math.cos(2*angle)+s2*Math.sin(2*angle))/2);
}

function drawAnalyzer(current,zero){
  const plot=$('analyzer-plot');
  const width=Math.round(plot.clientWidth);
  if(!width)return;
  const height=Math.min(width,360);
  const center=[width/2,height/2];
  const radius=Math.min(width,height)/2-29;
  const maxIntensity=Math.max(...[current,zero].map(([s0,s1,s2])=>(s0+Math.hypot(s1,s2))/2));
  const order=10**Math.floor(Math.log10(maxIntensity||1));
  const upper=(maxIntensity?Math.ceil(maxIntensity/order*2)/2:1)*order;
  const point=(r,angle)=>[center[0]+r*Math.cos(angle),center[1]-r*Math.sin(angle)];
  const selected=Number($('analyzer-angle').value);
  const angle=selected*Math.PI/180;
  plot.setAttribute('viewBox',`0 0 ${width} ${height}`);
  plot.setAttribute('height',height);
  plot.replaceChildren();
  const grid=svg('g',{class:'analyzer-grid'});
  for(const fraction of [.25,.5,.75,1]){
    grid.append(svg('circle',{cx:center[0],cy:center[1],r:radius*fraction}));
  }
  for(let degrees=0;degrees<360;degrees+=45){
    const radians=degrees*Math.PI/180;
    const [x2,y2]=point(radius,radians);
    grid.append(svg('line',{x1:center[0],y1:center[1],x2,y2}));
    if(degrees%90===0){
      const [x,y]=point(radius+15,radians);
      grid.append(svg('text',{x,y,'text-anchor':'middle','dominant-baseline':'central'},`${degrees}°`));
    }
  }
  const [tickX,tickY]=point(radius,Math.PI/3);
  grid.append(svg('text',{x:tickX+5,y:tickY-4,class:'radial-label'},precise(upper)));
  plot.append(grid);
  const [x2,y2]=point(radius,angle);
  plot.append(svg('line',{x1:center[0],y1:center[1],x2,y2,class:'selected-angle'}));
  const curves=[['analyzer-zero',zero],['analyzer-current',current]];
  for(const [name,stokes] of curves){
    const points=[];
    for(let degrees=0;degrees<=360;degrees+=2){
      const radians=degrees*Math.PI/180;
      const [x,y]=point(radius*analyzerIntensity(stokes,radians)/upper,radians);
      points.push(`${degrees?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`);
    }
    plot.append(svg('path',{id:name,d:points.join(' ')+' Z',class:'analyzer-curve',fill:'none'}));
  }
  for(const [name,stokes] of curves){
    const [cx,cy]=point(radius*analyzerIntensity(stokes,angle)/upper,angle);
    plot.append(svg('circle',{cx,cy,r:3.4,class:`analyzer-dot ${name}`}));
  }
  $('analyzer-angle-value').textContent=`${selected}°`;
  $('analyzer-reading').textContent=`当前 ${precise(analyzerIntensity(current,angle))} · 无 hBN ${precise(analyzerIntensity(zero,angle))}`;
}

function renderAnalyzer(){
  const d=result.maps;
  const ui=d.upper.indexOf(state.u),li=d.lower.indexOf(state.l);
  const i=index(ui,li),zeroIndex=ui*d.lower.length+li;
  const ref=result.reference_intensity;
  drawAnalyzer(['S0','S1','S2'].map(name=>d[name][i]/ref),d.zero_stokes.map(values=>values[zeroIndex]/ref));
}

function render(repaint){
  const d=result.maps,i=index(d.upper.indexOf(state.u),d.lower.indexOf(state.l));
  $('upper').value=state.u;$('lower').value=state.l;$('upper-value').textContent=state.u+' nm';$('lower-value').textContent=state.l+' nm';
  $('s3-value').textContent=fixed(d.s3[i]);$('polar-value').textContent='圆偏程度（绝对值）：'+fixed(Number.isFinite(d.s3[i])?Math.abs(d.s3[i]):null);
  const zeroIndex=d.upper.indexOf(state.u)*d.lower.length+d.lower.indexOf(state.l);
  $('reference-value').textContent=fixed(d.Q[i]);
  $('zero-value').textContent='无 hBN 对照 '+fixed(d.zero_stokes[0][zeroIndex]/result.reference_intensity);
  $('gain-value').textContent=Number.isFinite(d.G[i])?'当前信号是对照的 '+fixed(d.G[i])+' 倍':'无 hBN 对照的信号过弱，无法计算倍数。';
  const count=d.neighbors[i];
  $('min-value').textContent=count?fixed(d.minC[i]):'—';
  $('neighbors-value').textContent=count?`${count} 个组合 · 最低统一参考强度 ${fixed(d.minQ[i])}`:'当前为无 hBN 对照。';
  const testedSpacers=bootstrap.defaults.hbn.filter(h=>h>0&&Math.abs(h-state.h)<=5);
  $('neighbors-spacers').textContent=count?`hBN 取 ${testedSpacers.join('、')} nm，上下 Nb 取扫描范围内的 ±5 nm 与原厚度。`:'';
  $('result-label').textContent=`上 ${state.u} / hBN ${state.h} / 下 ${state.l} nm；转角 ${result.parameters.angle}°`;
  const defined=Number.isFinite(d.s3[i]);
  const normalized=[defined?1:null,d.s1[i],d.s2[i],d.s3[i]],raw=['S0','S1','S2','S3'].map(k=>d[k][i]);
  $('stokes-table').replaceChildren();
  const meanings=['总强度','x 与 y 分量的强度差','+45° 与 −45° 分量的强度差','两种圆偏分量的强度差'];
  for(let j=0;j<4;j++){const tr=document.createElement('tr');for(const text of ['S'+j,meanings[j],precise(raw[j]/result.reference_intensity),fixed(normalized[j])]){const td=document.createElement('td');td.textContent=text;tr.append(td);}$('stokes-table').append(tr);}
  ellipse(i);renderAnalyzer();for(const c of charts){if(repaint)paint(c);marker(c);}
  for(const button of document.querySelectorAll('.presets button'))button.setAttribute('aria-pressed',String(Number(button.dataset.u)===state.u&&Number(button.dataset.h)===state.h&&Number(button.dataset.l)===state.l));
}
async function spacerChanged(){if(!result)return;const h=Number($('spacer').value);if(!dirty&&result.maps.hbn.includes(h)){state.h=h;render(true);}else{dirtySettings();await calculate();}}
async function init(){
  try{
    const response=await fetch('/api/bootstrap');
    if(!response.ok)throw new Error('无法读取程序数据。');
    bootstrap=await response.json();result=await withBaselineMaps(bootstrap.result);materialInputs();
    $('spacer').replaceChildren(...bootstrap.defaults.hbn.map(h=>new Option(h?`${h} nm`:'0 nm · 无插层',h,false,h===state.h)));
    for(const value of intensityTicks){
      const text=document.createElement('span');
      text.textContent=value===intensityTicks.at(-1)?`≥${value}`:String(value);
      text.style.left=`${intensityScale(value)*100}%`;
      $('intensity-legend').append(text);
    }
    makeChart('intensity-map','intensity');makeChart('stokes-map','s3');
    const observer=new ResizeObserver(()=>charts.forEach(layout));for(const c of charts){layout(c);observer.observe(c.el.parentElement);}
    const analyzerResize=new ResizeObserver(renderAnalyzer);analyzerResize.observe($('analyzer-plot').parentElement);
    render(false);$('mode').textContent='默认基线 · 条件预测';statusForResult();
    $('settings').addEventListener('submit',e=>{e.preventDefault();calculate();});
    $('angle').addEventListener('input',dirtySettings);$('linear-angle').addEventListener('input',dirtySettings);
    $('input').addEventListener('change',()=>{$('linear-field').hidden=$('input').value!=='linear';dirtySettings();});
    $('spacer').addEventListener('change',spacerChanged);
    $('analyzer-angle').addEventListener('input',renderAnalyzer);
    for(const id of ['upper','lower'])$(id).addEventListener('input',()=>{if(dirty||busy)return;state[id==='upper'?'u':'l']=Number($(id).value);render(false);});
    $('reset-materials').addEventListener('click',()=>{for(const input of $('materials').querySelectorAll('input'))input.value='';dirtySettings();});
    for(const button of document.querySelectorAll('.presets button'))button.addEventListener('click',async()=>{if(busy)return;state.u=Number(button.dataset.u);state.l=Number(button.dataset.l);$('spacer').value=button.dataset.h;await spacerChanged();});
  }catch(error){showStatus(error.message,'error');}
}
init();
