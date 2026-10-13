const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => value == null ? '—' : value.toFixed(2);
const percent = value => value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
const money = value => value == null ? '—' : value >= 1e12 ? `${(value/1e12).toFixed(2)} 万亿` : `${(value/1e8).toFixed(2)} 亿`;
const tone = value => value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
const date = value => value ? `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}` : '暂无数据';
const notes = {
  classic:'黑底、金色导航、紧凑行高，尽量在一屏内比较更多股票。适合习惯传统行情终端的使用方式。',
  dark:'炭灰底搭配橙色导航，列表与个股资料清晰分区。适合夜间看盘与连续浏览。',
  light:'蓝色只用于导航和筛选，红绿专门表达涨跌。适合白天浏览板块和比较公司。',
  paper:'柔和灰白底、墨绿导航、更宽松的行距，强调代表性说明。适合慢慢了解行业和公司。'
};
function setTheme(theme) {
  if (!notes[theme]) theme = 'light';
  document.body.dataset.theme = theme;
  document.querySelectorAll('.theme-options button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.theme === theme)));
  $('#design-note').textContent = notes[theme];
  history.replaceState(null, '', `#${theme}`);
}
document.querySelectorAll('.theme-options button').forEach(button => button.addEventListener('click', () => setTheme(button.dataset.theme)));
setTheme(location.hash.slice(1));
let industry = '', scope = 'representatives', sort = 'default', page = 1, totalPages = 1;
let stocks = [], listAbort, detailAbort, selectedId, debounce;
async function get(path, signal) {
  const response = await fetch(`/api${path}`, {signal});
  if (!response.ok) throw new Error(`数据读取失败 (${response.status})`);
  return response.json();
}
function renderIndustries(items) {
  $('#industry-list').innerHTML = [{id:'', name:'全部行业', stock_count:items.reduce((n,i)=>n+i.stock_count,0)},...items].map(i=>`<button data-id="${escapeHTML(i.id)}" class="${i.id === industry ? 'active' : ''}">${escapeHTML(i.name)}<span>${i.stock_count}</span></button>`).join('');
  $('#industry-list').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    industry = b.dataset.id;
    $('#industry-title').textContent = items.find(i=>i.id===industry)?.name || '全部行业';
    $('#industry-list').querySelectorAll('button').forEach(item=>item.classList.toggle('active',item===b));
    page = 1; loadStocks();
  }));
}
function renderRows() {
  $('#rows').innerHTML = stocks.map((s,index)=>`<tr data-id="${s.id}" class="${s.id===selectedId?'selected':''}"><td class="ordinal">${(page-1)*20+index+1}</td><td><button class="stock-name">${escapeHTML(s.name)}</button><span class="stock-code">${escapeHTML(s.code)}</span></td><td class="industry-cell">${escapeHTML(s.industry)}</td><td class="numeric ${tone(s.pct_chg)}">${number(s.close)}</td><td class="numeric ${tone(s.pct_chg)}">${percent(s.pct_chg)}</td><td class="numeric">${money(s.amount)}</td><td class="numeric">${money(s.market_cap)}</td></tr>`).join('');
  $('#rows').querySelectorAll('tr').forEach(row => row.addEventListener('click',()=>selectStock(stocks.find(s=>s.id===Number(row.dataset.id)))));
}
async function loadStocks() {
  listAbort?.abort(); detailAbort?.abort();
  const controller = listAbort = new AbortController();
  $('#list-message').textContent = '正在读取行情…';
  $('#rows').innerHTML = '';
  $('#stock-panel').innerHTML = '<p class="muted">正在读取…</p>';
  $('#prev').disabled = $('#next').disabled = true;
  const params = new URLSearchParams({scope,sort,page:String(page),page_size:'20',group_by:'none',keyword:$('#search').value});
  if (industry) params.set('industry_id', industry);
  if ($('#board').value) params.set('board',$('#board').value);
  try {
    const result = await get(`/stocks?${params}`, controller.signal);
    stocks = result.items;
    totalPages = Math.max(1,Math.ceil(result.total/20));
    $('#result-count').textContent = `${result.matched_stocks.toLocaleString()} 只股票`;
    $('#page-label').textContent = `${page} / ${totalPages}`;
    $('#prev').disabled = page<=1; $('#next').disabled = page>=totalPages;
    $('#quote-date').textContent = `行情 ${date(result.trade_date)}`;
    $('#list-message').textContent = stocks.length ? '' : '没有匹配的股票';
    selectedId = stocks[0]?.id;
    renderRows();
    if (stocks[0]) selectStock(stocks[0]);
    else $('#stock-panel').innerHTML = '<p class="muted">暂无股票资料</p>';
  } catch(error) {
    if (error.name==='AbortError') return;
    $('#list-message').textContent = `${error.message}，请刷新重试`;
    $('#stock-panel').innerHTML = '<p class="muted">暂时无法读取资料</p>';
  }
}
async function selectStock(stock) {
  detailAbort?.abort();
  const controller = detailAbort = new AbortController();
  selectedId = stock.id; renderRows();
  $('#stock-panel').innerHTML = `<p class="panel-label">${stock.representative?'行业代表公司':'个股速览'}</p><h2>${escapeHTML(stock.name)}</h2><div class="security">${escapeHTML(stock.code)} · ${escapeHTML(stock.board)}</div><div class="big-quote ${tone(stock.pct_chg)}">${number(stock.close)}</div><div class="quote-change ${tone(stock.pct_chg)}">${percent(stock.pct_chg)} <span class="muted"> / 收盘</span></div><div class="chart-heading"><span>近一个月 · 前复权</span><span id="chart-state">读取中</span></div><div class="chart" id="chart"></div><div class="chart-dates" id="chart-dates"></div><dl class="metrics"><div><dt>总市值</dt><dd>${money(stock.market_cap)}</dd></div><div><dt>成交额</dt><dd>${money(stock.amount)}</dd></div><div><dt>所属行业</dt><dd>${escapeHTML(stock.industry)}</dd></div><div><dt>上市时间</dt><dd>${date(stock.list_date)}</dd></div></dl><h3>${stock.representative?'代表性说明':'公司资料'}</h3><p class="reason">${escapeHTML(stock.representative?.reason || stock.main_business || '暂无公司资料')}</p><a class="detail-link" href="/stocks/${stock.id}">查看完整资料 ↗</a>`;
  try {
    const result = await get(`/stocks/${stock.id}/prices?range=1m`,controller.signal);
    if (selectedId !== stock.id) return;
    const values = result.points.filter(p=>p.price!=null).map(p=>p.price);
    if (values.length<2) {
      $('#chart').innerHTML = `<div class="chart-empty">${result.pending?'历史数据补齐中':'暂无价格走势'}</div>`;
      $('#chart-state').textContent = '待补齐'; return;
    }
    const min = Math.min(...values), max = Math.max(...values), spread = max-min || 1;
    let path='', penDown=false;
    result.points.forEach((p,i)=>{
      if(p.price==null){penDown=false;return;}
      path += `${penDown?'L':'M'}${(i/(result.points.length-1)*200).toFixed(2)},${(90-(p.price-min)/spread*80).toFixed(2)} `;penDown=true;
    });
    $('#chart').innerHTML = `<svg viewBox="0 0 200 100" preserveAspectRatio="none" role="img" aria-label="近一个月前复权收盘价格走势"><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
    $('#chart-state').textContent = result.complete?'日线':'有缺口';
    $('#chart-dates').innerHTML = `<span>${date(result.points[0].date)}</span><span>${date(result.points.at(-1).date)}</span>`;
  } catch(error) {
    if(error.name==='AbortError') return;
    $('#chart-state').textContent = '读取失败';
    $('#chart').innerHTML = '<div class="chart-empty">暂时无法读取历史价格</div>';
  }
}
document.querySelectorAll('.market-tabs button').forEach(button=>button.addEventListener('click',()=>{
  const view=button.dataset.view;
  scope=view==='representatives'?'representatives':'all';
  sort=view.startsWith('pct_')?view:'default';
  $('#sort').value=sort;
  document.querySelectorAll('.market-tabs button').forEach(b=>b.classList.toggle('active',b===button));
  page=1;loadStocks();
}));
$('#search').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{page=1;loadStocks();},300);});
$('#board').addEventListener('change',()=>{page=1;loadStocks();});
$('#sort').addEventListener('change',()=>{
  sort=$('#sort').value;
  const view = scope==='representatives'?'representatives':sort.startsWith('pct_')?sort:'all';
  document.querySelectorAll('.market-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  page=1;loadStocks();
});
$('#prev').addEventListener('click',()=>{if(page>1){page--;loadStocks();}});
$('#next').addEventListener('click',()=>{if(page<totalPages){page++;loadStocks();}});
get('/industries').then(renderIndustries).catch(()=>{$('#industry-list').textContent='行业数据读取失败';});
get('/data-status').then(s=>{
  $('#source').textContent=`${s.source} · ${s.missing_quote_count} 只暂无有效行情${s.stale?' · 当前为旧数据':''}`;
}).catch(()=>{$('#source').textContent='数据状态读取失败';});
loadStocks();
