import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { models, staleRecord } from './catalog.js';
import { protocolNames, protocolExample } from './protocol-examples.js';
import { modelGuide } from './model-learning.js';
import { pretty } from './inspect-panels.js';
const lang = () => document.documentElement.lang === 'en' ? 'en' : 'zh';
const l = pair => pair ? tr(...pair) : '';
export const academyUrl = params => '/academy?' + new URLSearchParams({ lang: lang(), ...params });
export const unknown = value => value == null ? tr('待补充', 'Not documented here') : typeof value === 'boolean' ? (value ? tr('支持', 'Supported') : tr('不支持', 'Unsupported')) : Array.isArray(value) ? value.join(', ') : typeof value === 'number' ? value.toLocaleString('en-US') : String(value);
export function priceText(price, now = Date.now()) {
  if (!price) return tr('费率待补充', 'Rates not documented here');
  const rates = [[tr('输入','Input'),price.input],[tr('输出','Output'),price.output],[tr('缓存读取','Cache read'),price.cached_input]].filter(([,v])=>v!=null).map(([name,value])=>`${name} $${value}`).join(' · ');
  const expired = price.valid_through && now > Date.parse(price.valid_through + 'T23:59:59Z');
  return `${expired ? tr('已过期，需复核 · ','Expired, review needed · ') : ''}${price.currency} · ${rates} / ${price.unit}${price.valid_through ? ' · '+tr('有效至 ','Valid through ')+price.valid_through : ''}`;
}
export function exampleForModel(model, second = true) {
  const raw = protocolExample(model.protocol, second);
  if (model.model_id && model.protocol !== 'gemini') raw.model = model.model_id;
  return raw;
}
function modelFields(m) {
  const fields = [[tr('任务','Task'),m.task],[tr('部署','Deployment'),m.access],[tr('API / 权重 ID','API / weight ID'),m.model_id],[tr('输入','Input'),m.input_modalities],[tr('输出','Output'),m.output_modalities],[tr('上下文 / 输入上限（token）','Context / input limit (tokens)'),m.context_window],[tr('最大输出（token）','Max output (tokens)'),m.max_output],[tr('架构','Architecture'),m.architecture],[tr('参数量','Parameters'),m.parameters],[tr('向量维度','Embedding dimensions'),m.embedding_dimensions],[tr('工具调用','Tool calling'),m.tool_support],[tr('严格结构化输出','Structured output'),m.structured_output],[tr('权重许可','Weight license'),m.license],[tr('生命周期','Lifecycle'),m.lifecycle==='not-verified'?null:m.lifecycle],[tr('发布时间','Released'),m.published_on],[tr('替代关系','Replaces'),m.replaces]];
  const optional = new Set([tr('生命周期','Lifecycle'),tr('发布时间','Released'),tr('替代关系','Replaces')]);
  if(m.task!=='embedding')optional.add(tr('向量维度','Embedding dimensions'));
  if(m.access!=='open-weight')optional.add(tr('权重许可','Weight license'));
  if(!['text','image'].includes(m.task))optional.add(tr('最大输出（token）','Max output (tokens)'));
  if(m.task!=='text'){optional.add(tr('工具调用','Tool calling'));optional.add(tr('严格结构化输出','Structured output'));}
  if(m.access!=='open-weight'){optional.add(tr('架构','Architecture'));optional.add(tr('参数量','Parameters'));}
  return fields.filter(([name,value])=>value!=null||!optional.has(name));
}
export function modelCard(m, compared) {
  return `<article class="ax-card"><small>${esc(m.provider)} · ${esc(m.family)}</small><h3><a href="${esc(academyUrl({model:m.id}))}">${esc(m.name)}</a></h3><span class="ax-tag">${esc(m.task)}</span><span class="ax-tag">${esc(m.access)}</span><p class="ax-model-summary">${esc(l(m.summary))}</p><dl class="ax-card-specs">${[[tr('上下文','Context'),m.context_window],[tr('输出','Output'),m.output_modalities],[tr('许可','License'),m.license]].filter(([,v])=>v!=null).map(([name,value])=>`<div><dt>${name}</dt><dd>${esc(unknown(value))}</dd></div>`).join('')}</dl>${m.pricing?`<p class="ax-card-price">${esc(priceText(m.pricing))}</p>`:''}<label><input type="checkbox" data-model-compare="${m.id}" ${compared.has(m.id)?'checked':''}> ${tr('加入对比（最多3项）','Compare (up to 3)')}</label><p>${tr('资料核验','Checked')}: ${m.verified_on}${staleRecord(m)?' · '+tr('需复核','Review needed'):''}</p></article>`;
}
export function modelDetail(m) {
  const fields=modelFields(m), guide=modelGuide(m);
  return `<section class="ax-study"><a href="${academyUrl({tab:'models'})}">← ${tr('模型库','Models')}</a><small class="ax-detail-kicker">${esc(m.provider)} / ${esc(m.family)}</small><h2>${esc(m.name)}</h2><p class="ax-lead">${esc(l(m.summary))}</p><div class="ax-fact-grid">${[[tr('上下文 / 输入上限（token）','Context / input limit (tokens)'),m.context_window],[tr('最大输出（token）','Max output (tokens)'),m.max_output],[tr('输入 → 输出','Input → output'),m.input_modalities&&m.output_modalities?unknown(m.input_modalities)+' → '+unknown(m.output_modalities):null]].filter(([,v])=>v!=null).map(([name,v])=>`<div><small>${name}</small><b>${esc(unknown(v))}</b></div>`).join('')}</div><p class="cx-note">${esc(l(m.notes))}</p><h3>${tr('怎样理解这类模型','How this kind of model works')}</h3><h4>${esc(l(guide.title))}</h4><div class="ax-pipeline">${guide.steps.map((step,i)=>`<div><small>0${i+1}</small><b>${esc(l(step))}</b></div>`).join('')}</div><p>${esc(l(guide.learn))}</p><div class="ax-exercise"><b>${tr('可以动手验证什么？','What can you check?')}</b><p>${esc(l(guide.exercise))}</p>${guide.lesson?`<a href="${academyUrl({tab:'lessons',lesson:guide.lesson})}">${tr('进入相关学习案例 →','Open a related lesson →')}</a>`:`<p>${tr('此任务尚无本站执行案例；上方是原理讲解，不展示虚构生成结果。','No execution fixture is provided for this task yet; the flow explains concepts without inventing generated output.')}</p>`}</div><h3>${tr('已整理的规格','Documented specifications')}</h3><div class="ax-table-wrap"><table class="ax-table"><tbody>${fields.filter(([,v])=>v!=null).map(([name,value])=>`<tr><th>${name}</th><td>${esc(unknown(value))}</td></tr>`).join('')}</tbody></table></div><details class="ax-unknown"><summary>${tr('尚未整理的字段','Fields still to document')} · ${fields.filter(([,v])=>v==null).length}</summary><p>${fields.filter(([,v])=>v==null).map(([name])=>name).join(' · ')}</p><p>${tr('空缺不等于不支持；以具体型号与服务平台的官方资料为准。','Missing information does not mean unsupported. Check the specific model and serving platform.')}</p></details>${m.pricing?`<h3>${tr('官方费用与计费条件','Official pricing and conditions')}</h3><p class="ax-price">${esc(priceText(m.pricing))}</p><p>${esc(l(m.pricing.note))}</p>`:''}${m.protocol?`<h3>${tr('一次请求长什么样','What a request looks like')}</h3><p>${esc(protocolNames[m.protocol])} · ${tr('人工协议示例，未调用该模型；兼容协议也可能有不同的参数和工具约束。','Authored protocol example, not a model run; compatible APIs may have different parameter/tool constraints.')}</p><a class="ax-open-inspector" href="/context?${new URLSearchParams({lang:lang(),protocol:m.protocol,model:m.id})}">${tr('打开可交互解剖台 →','Open interactive inspector →')}</a><details><summary>${tr('展开示例原始请求','Show example request')}</summary>${pretty(exampleForModel(m))}</details>`:''}<h3>${tr('来源与核验范围','Sources and verification')}</h3><p>${tr('核验日期','Checked')}: ${m.verified_on} · ${tr('资料核验，不是本站运行实测。','Documentation review, not a local execution test.')}</p><ul>${(m.references||[{url:m.source,label:'Official reference'}]).map(ref=>`<li><a href="${esc(ref.url)}" target="_blank" rel="noopener noreferrer">${esc(tr(ref.label === 'Pricing and effective dates' ? '定价与生效日期' : '官方型号资料', ref.label))} ↗</a></li>`).join('')}</ul><a href="/feed?${new URLSearchParams({lang:lang(),q:m.name})}">${tr('查看相关资讯 →','Related updates →')}</a></section>`;
}
export function modelComparison(ids) {
  const chosen=[...ids].map(id=>models.find(m=>m.id===id)).filter(Boolean);if(!chosen.length)return '';
  const fields=[[tr('提供方','Provider'),'provider'],[tr('任务','Task'),'task'],[tr('上下文','Context'),'context_window'],[tr('最大输出（token）','Max output (tokens)'),'max_output'],[tr('输入','Input'),'input_modalities'],[tr('输出','Output'),'output_modalities'],[tr('工具','Tools'),'tool_support'],[tr('参数量','Parameters'),'parameters'],[tr('许可','License'),'license'],[tr('价格与单位','Rates and units'),'pricing']].filter(([,key])=>chosen.some(m=>m[key]!=null));
  return `<section class="ax-study"><h3>${tr('模型资料对照','Model reference comparison')}</h3><div class="ax-table-wrap"><table class="ax-table"><thead><tr><th></th>${chosen.map(m=>`<th>${esc(m.name)}</th>`).join('')}</tr></thead><tbody>${fields.map(([name,key])=>`<tr><th>${name}</th>${chosen.map(m=>`<td>${esc(key==='pricing'?priceText(m.pricing):unknown(m[key]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p>${tr('不同计费单位和条件不能直接比较；详细费率条件请进入型号详情。上下文上限也不代表长文理解可靠性。','Different billing units/conditions are not directly comparable; open details for pricing conditions. Context limits do not measure long-document reliability.')}</p></section>`;
}
