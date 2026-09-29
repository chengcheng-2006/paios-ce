(function () {
  'use strict';
  const base = 'SCREEN_';
  const screens = [
    ['01_EXECUTION_PROOF.html', '01 受治理执行'],
    ['02_VERIFIER_CONTROL.html', '02 验收与完成'],
    ['03_ACTION_AWARE_RECOVERY.html', '03 异常恢复'],
    ['04_GENERIC_AGENT_VS_ASTRON.html', '04 执行职责']
  ];
  // Translate display strings only. The replay JSON remains the unchanged
  // source of record, and canonical IDs/paths remain available in references.
  const translations = {
    'SUCCEEDED':'已成功', 'VERIFIED':'已验证', 'NOT_RECORDED':'未记录', 'ALLOW':'已授权',
    'USER_DELIVERABLE':'用户交付物', 'MATCH':'一致', 'ACCEPTED':'已接受', 'TASK_SUCCEEDED':'任务已成功',
    'PASS':'通过', 'REFUSED':'已拒绝', 'PROPOSE_COMPLETE':'提议完成', 'NOT SUCCESS YET':'尚未成功',
    'QUALIFIED_RUNTIME_TESTED_WINDOWS':'经限定的运行时／测试故障窗口证据',
    'TASK_CREATED':'任务已创建', 'PLAN_CREATED':'计划已创建', 'MODEL_DECISION':'模型决策',
    'ACTION_PROPOSED':'已提议动作', 'ACTION_AUTHORIZED':'动作已获授权', 'ACTION_SUCCEEDED':'动作已成功',
    'ARTIFACT_REGISTERED':'交付物已登记', 'VERIFICATION_STARTED':'开始验收',
    'VERIFICATION_RESULT: ACCEPT':'验收结果：通过', 'VERIFICATION_ACCEPTED':'验收已通过',
    'AUTHORIZED':'执行已获授权', 'ATTEMPT_STARTED':'执行尝试已开始', 'OUTCOME UNKNOWN':'执行结果未知',
    'UNCERTAIN':'状态未明', 'RECONCILIATION':'对账确认', 'CONFIRMED_SUCCEEDED':'已确认成功',
    'CONFIRMED_NOT_APPLIED':'已确认未执行', 'NO_EVIDENCE':'暂无证据',
    'Corrupt artifact':'交付物已损坏', 'AC-CeilingRaised':'限流上限已提高',
    'AC-ReportDelivered':'报告已交付', 'Real-model tasks proven':'已验证真实模型任务',
    'Model decisions':'模型决策次数', 'Executed actions':'已执行动作', 'Journal coverage':'日志记录覆盖',
    'Harness bypass':'绕过运行时的情况', 'Artifact digest':'交付物摘要校验',
    'Acceptance criteria':'验收标准', 'Final state':'最终状态', '0 observed':'观察到 0 次',
    '2 / 2 PASS':'2 / 2 项通过', '128 B':'128 字节',
    'Raise limiter MAX_RPS from 10 to 20':'将限流器 MAX_RPS 从 10 提高到 20',
    'Real workspace change':'真实工作区变更', 'Forbidden mutations observed':'观察到的越界变更',
    'One precise patch action in the five-action task':'五项动作中的一次精准补丁修改',
    'Specific tool name is not included in the public replay sources':'公开回放资料未提供具体工具名称',
    'Journaled; per-action record present in canonical proof':'已记入日志；规范实证中包含逐项记录',
    'Change MAX_RPS only, from 10 to 20':'仅将 MAX_RPS 从 10 调整至 20',
    'Execution receipts are in the canonical proof; no per-action receipt identifier is shown in this replay.':'规范实证中包含执行回执；本回放未展示逐项回执编号。',
    'A model tool request is not the same thing as an executed action.':'模型提出工具调用请求，不等于动作已经执行。',
    'Model proposes completion; verification has not yet accepted the task.':'模型提出任务完成，但验收尚未通过。',
    'The model proposes completion; verification has not yet accepted the task.':'模型可以提出完成，但不能自行宣布任务成功。',
    'Separate retained deterministic summary; not part of the positive proof or a new/replayed run. Original per-process output unavailable for line-by-line review.':'单独保留的确定性摘要；不属于成功实证，也不是新运行或回放。原始进程输出已无法逐行复核。',
    'Observed only within saved intents, journals, receipts, application events, and captured scope; not an OS-wide audit.':'仅检查已保存的意图、日志、回执、应用事件及捕获范围；并非操作系统级审计。',
    'Based on saved task intents, application records, and checked before/after workspace evidence; not an OS-wide or all-process filesystem audit.':'依据已保存的任务意图、应用记录及变更前后的工作区证据；并非操作系统级或全进程文件系统审计。',
    'Original per-process output directory unavailable for line-by-line reinspection in this review.':'本次复核无法取得原始进程输出目录进行逐行检查。',
    'Model proposal; not an executed action.':'模型提出的建议；尚未执行。',
    'Runtime authorization precedes the attempt.':'动作尝试开始前须先经运行时授权。',
    'The attempt boundary is durably recorded before execution.':'执行前会先持久记录动作尝试的起点。',
    'Interruption without a trustworthy terminal result.':'流程中断，且没有可信的最终结果。',
    'Keep the action unresolved and reconcile before retrying.':'保留未决状态；重试前先进行对账确认。',
    'Check trusted external facts before deciding what happens next.':'先核对可信的外部事实，再决定后续处理。',
    'No arbitrary exactly-once or production-scale reliability claim.':'不宣称任意场景下恰好执行一次，也不宣称已具备生产规模的可靠性。',
    'Timeout ≠ no side effect.':'超时 ≠ 没有副作用。',
    'Reconcile against trusted external facts before deciding what happens next.':'先依据可信的外部事实进行对账，再决定后续处理。',
    'Terminal success; do not execute again.':'已确认最终成功；不要再次执行。',
    'Retry eligible only after trusted confirmation; an explicit call is still required.':'只有可信证据确认动作未执行后，才具备重试条件；仍须显式发起调用。',
    'Remain uncertain; no retry eligibility.':'维持状态未明；不具备重试条件。',
    'GENERIC TOOL-CALLING AGENT':'通用工具调用智能体', 'User':'用户', 'LLM / Agent Loop':'大语言模型／智能体循环',
    'Tool Call':'工具调用', 'Tool':'工具', 'Final Answer':'最终答复',
    'Agent Intelligence':'智能体决策', 'Action Proposal':'动作提议', 'Runtime Authorization':'运行时授权',
    'Governed Execution':'受治理的执行', 'Durable Facts / Artifact':'持久化事实／交付物',
    'Verifier':'验收器', 'Accepted Completion':'验收通过后完成',
    'Astron changes execution responsibility, not model intelligence.':'Astron 改变的是执行责任归属，而非模型智能。',
    'This illustration does not claim generic agents lack authorization, durable records, or verification; no comparative outcome was measured.':'此图不表示通用智能体缺少授权、持久记录或验收能力；本图也未测量或比较双方结果。'
  };
  const zh = (value) => translations[String(value)] || String(value);
  const claimSummary = (value) => {
    const s = String(value || '');
    if (s.startsWith('Evidence board metric:')) return '证据概览指标：观察到绕过运行时的情况为 0 次';
    if (s.startsWith('Scene 1 artifact card:')) return '第 1 页交付物卡片：展示交付物路径、记录的 SHA-256 摘要及独立重算结果；两者一致';
    if (s.startsWith('Scene 1 count cards:')) return '第 1 页数量卡片：5 次服务方调用、5 次模型决策、5 项已提议／已授权／已执行并记入日志的动作';
    if (s.startsWith('Scene 1 neutral responsibility comparison inset:')) return '第 1 页职责对照示意：并列展示通用工具调用流程与 Astron 的授权、动作记录及验收阶段';
    if (s.startsWith('Scene 1 optional model-ID footnote')) return '第 1 页模型 ID 说明';
    if (s.startsWith('Scene 1 task scope card:')) return '第 1 页任务范围卡片：MAX_RPS 从 10 调整至 20；其他两项常量保持不变';
    if (s.startsWith('Scene 1 title and proof identity:')) return '第 1 页标题与实证标识：ASTRON_REAL_MODEL_END_TO_END_PROOF_V1';
    if (s.startsWith('Scene 2 acceptance criteria and durable status:')) return '第 2 页验收标准与持久状态：限流上限已提高=通过；报告已交付=通过；验收已接受；任务已成功';
    if (s.startsWith('Scene 2 memory hook:')) return '第 2 页提示语：AI 说完成，不等于任务真的完成。';
    if (s.startsWith('Scene 2 positive completion timeline:')) return '第 2 页成功完成顺序：提议完成 → 开始验收 → 验收结果通过 → 验收已通过 → 任务已成功';
    if (s.startsWith('Scene 2 separate retained negative example:')) return '第 2 页单独保留的负向示例：交付物损坏 → 验收拒绝；这是确定性故障矩阵示例，并非新运行';
    if (s.startsWith('Scene 3 persistent qualification banner:')) return '第 3 页资格说明：限定条件下的运行时／故障窗口证据，不属于成功实证';
    if (s.startsWith('Scene 3 raw-output limitation footer')) return '第 3 页原始输出复核限制说明';
    if (s.startsWith('Scene 3 recovery state diagram:')) return '第 3 页恢复状态图：动作提议 → 授权 → 开始尝试 → 结果未知 → 状态未明 → 可信对账；已确认成功后不重复执行；确认未执行后才具备重试条件，且仍须显式调用；暂无证据时不得重试。超时 ≠ 没有副作用。';
    if (s.startsWith('Scene 3 retained fault-matrix summary card:')) return '第 3 页保留的故障矩阵摘要：15/15';
    return '原始页面映射已保留在证据映射表中';
  };
  const sourceSummary = (value) => {
    const s = String(value || '');
    const refs = [...s.matchAll(/(?:outputs\/)?[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*\.(?:md|json)(?:\s*§{1,2}[\d,\s–-]+)?/g)].map(m => m[0].trim());
    const brief = [...s.matchAll(/(?:ASTRON_COMPETITION_VISUAL_PRODUCTION_V1 user brief|Visual Production V1)\s*§{1,2}[\d,\s–-]+/g)].map(m => m[0].replace('ASTRON_COMPETITION_VISUAL_PRODUCTION_V1 user brief', 'ASTRON_COMPETITION_VISUAL_PRODUCTION_V1 需求说明').replace('Visual Production V1', '可视化演示 V1').replace(/§{1,2}/g, ' 第 '));
    const all = [...new Set([...refs, ...brief])];
    return all.length ? `原始出处：${all.join('；')}` : '原始来源记录已保留在回放数据中';
  };
  const nav = document.getElementById('scene-nav');
  if (nav) nav.innerHTML = screens.map(([file, label], i) => `<a href="${base}${file}"${document.body.dataset.screen === String(i + 1) ? ' aria-current="page"' : ''}>${label}</a>`).join('');
  const app = document.getElementById('app');
  if (!app) return;
  const screen = Number(document.body.dataset.screen || 0);
  const escapeHTML = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ref = (item, value, label = '') => {
    const shown = value === undefined ? item.value : value;
    const shownText = Array.isArray(shown) ? shown.map(zh).join(' → ') : typeof shown === 'object' && shown !== null ? JSON.stringify(shown) : zh(shown);
    const sourceLabel = label || '查看证据来源与主张映射';
    return `<span class="evidence-value">${escapeHTML(shownText)}</span><details class="source"><summary aria-label="${escapeHTML(sourceLabel)}" title="${escapeHTML(sourceLabel)}"><span class="visually-hidden">${escapeHTML(sourceLabel)}</span></summary><dl><dt>证据来源</dt><dd>${escapeHTML(sourceSummary(item.source_reference))}</dd><dt>主张映射</dt><dd>${escapeHTML(claimSummary(item.claim_map_ref))}</dd></dl><a href="../demo_evidence/06_EVIDENCE_TO_SCREEN_MAP.json" target="_blank" rel="noopener">打开证据与页面映射表</a></details>`;
  };
  const metric = (item) => `<article class="metric"><span class="metric-label">${escapeHTML(zh(item.label))}</span><strong>${ref(item, item.display_value, '证据来源')}</strong></article>`;
  const fact = (x, key) => x[key];
  const badge = '<span class="recorded-badge"><i aria-hidden="true"></i> 已记录并验收通过</span>';
  const replayBadges = {
    0: '<span class="recorded-badge"><i aria-hidden="true"></i> 证据回放</span>',
    1: badge,
    2: badge,
    3: '<span class="recorded-badge"><i aria-hidden="true"></i> 限定条件下的证据回放</span>',
    4: '<span class="recorded-badge"><i aria-hidden="true"></i> 说明性证据回放</span>'
  };
  const header = (eyebrow, title, sub='') => `<div class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1>${sub ? `<p class="subhead">${sub}</p>` : ''}</div>${replayBadges[screen] || replayBadges[0]}</div>`;
  const taskcard = (f) => `<section class="panel task-card"><div class="panel-head"><span class="panel-kicker">有界任务</span><div class="status-pair"><span class="state-chip success">${ref(f.task_status, undefined, '任务状态来源')}</span><span class="state-chip success">${ref(f.completion_label, undefined, '验收标签来源')}</span></div></div><div class="task-goal">${ref(f.task_goal)}</div><div class="proof-id">${ref(f.proof_id)}</div><div class="model-caveat"><span>请求的模型 ID</span><strong>${ref(f.requested_model_id, undefined, '模型身份来源')}</strong><small>服务方返回的模型身份：${ref(f.provider_returned_model_identity, undefined, '身份说明来源')}</small></div></section>`;
  const count = (label, item, display) => `<div class="count-card"><span>${label}</span><strong>${ref(item, display === undefined ? item.value : display, '数量来源')}</strong></div>`;
  function scene1(d) {
    const f=d.facts;
    const completionEvents=f.timeline.filter(e=>e.kind === 'recorded_event');
    const timeline=f.timeline.filter(t=>t.kind !== 'recorded_event').map(t=>`<li class="phase"><span class="phase-dot"></span><div><strong>${ref(t,t.label,'阶段证据')}</strong><small>${t.count !== undefined ? ref(t,t.count,'已记录数量来源') : '阶段标签未记录时间'}</small></div></li>`).join('');
    return `${header('场景 01 / 执行实证','一项边界明确的任务，全程受治理。','已记录证据回放 · 完成判定顺序见第 02 页')}
      <div class="proof-grid">${taskcard(f)}<section class="panel timeline-panel"><div class="panel-head"><div><span class="panel-kicker">执行路径</span><h2>证据阶段</h2></div><span class="micro-label">未记录时间，不代表事件位置</span></div><ol class="timeline">${timeline}</ol><div class="count-grid">${count('服务方调用',f.provider_calls)}${count('已提议动作',f.proposed_actions)}${count('已授权动作',f.authorized_actions)}${count('已执行动作',f.executed_actions)}${count('已记入日志',f.journaled_executed_actions,f.journaled_executed_actions.display_value)}</div></section><section class="panel action-panel"><div class="panel-head"><span class="panel-kicker">动作详情</span><span class="state-chip success">${ref(f.selected_action_detail.execution_status)}</span></div><h2>${ref(f.selected_action_detail.action_type)}</h2><div class="action-chain"><span>已提议 <b>${ref(f.proposed_actions,f.proposed_actions.value,'提议数量来源')}</b></span><i>→</i><span>已授权 <b>${ref(f.authorized_actions,f.authorized_actions.value,'授权数量来源')}</b></span><i>→</i><span>已执行 <b>${ref(f.executed_actions,f.executed_actions.value,'执行数量来源')}</b></span></div><p class="distinction">${ref(f.selected_action_detail.request_execution_distinction)}</p><dl class="detail-list"><div><dt>授权状态</dt><dd>${ref(f.selected_action_detail.authorization)}</dd></div><div><dt>日志记录</dt><dd>${ref(f.selected_action_detail.journal_status)}</dd></div><div><dt>工具身份</dt><dd>${ref(f.selected_action_detail.tool_identity)}</dd></div><div><dt>动作回执</dt><dd>${ref(f.selected_action_detail.receipt_note)}</dd></div></dl><div class="code-diff"><span>${ref(f.source_change.display_label)}</span><code>${ref(f.source_change.before)}</code><code>${ref(f.source_change.after)}</code></div><small class="scope-note">${zh(f.source_change.forbidden_mutations_label.value)}：${ref(f.source_change.forbidden_mutations_observed, `${f.source_change.forbidden_mutations_observed.value}`, '范围说明')} · ${escapeHTML(zh(f.source_change.forbidden_mutations_observed.scope_note))}</small></section></div>
      <section class="panel event-sequence"><div class="panel-head"><div><span class="panel-kicker">已记录的完成顺序</span><h2>事件位置 43–47</h2></div><span class="micro-label">按记录顺序排列 · 未提供时间戳</span></div><div class="sequence">${completionEvents.map(e=>`<span class="event">${ref(e,e.event_number,'已记录事件位置')}<b>${ref(e,e.label,'事件来源')}</b></span>`).join('')}</div></section>
      <section class="panel artifact-strip"><div><span class="panel-kicker">交付物类别 · 本演示使用的标签 ${ref(f.artifact.type)}</span><strong>${ref(f.artifact.path)}</strong><small>${ref(f.artifact.size_bytes,f.artifact.size_bytes.display_value,'交付物大小来源')} · SHA-256 摘要：${ref(f.artifact.digest_result)} · 状态：${ref(f.artifact.status)}</small></div><code>${ref(f.artifact.recorded_sha256,undefined,'已记录的摘要值')}</code></section>
      <section class="metric-board"><div class="board-title"><div><span class="panel-kicker">证据概览</span><h2>一次已记录的运行</h2></div><span class="micro-label">8 项已记录指标</span></div>${f.evidence_board.map(item => item.label === 'Harness bypass' ? `<article class="metric limitation"><span class="metric-label">${escapeHTML(zh(item.label))}</span><strong>${ref(f.harness_bypass_observed,item.display_value,'限定范围内的证据')}</strong><small>${escapeHTML(zh(f.harness_bypass_observed.scope_note))}</small></article>` : metric(item)).join('')}</section><p class="bottom-note">${ref(f.source_change.other_two_constants_retained,'其他两项常量保持不变','范围确认')}</p>`;
  }
  function scene2(d) {
    const f=d.facts, v=f.verification, c=f.source_change, a=f.artifact;
    const neg=v.retained_negative_example;
    const completionEvents=f.timeline.filter(e=>e.kind === 'recorded_event');
    return `${header('场景 02 / 验收判定','验收通过后，任务才算完成。',ref(v.supporting_line))}
      <section class="panel diff-panel"><div class="panel-head"><div><span class="panel-kicker">规范任务变更</span><h2>记录中恰有两行变更</h2></div></div><div class="diff-lines"><div>${ref(c.before)} </div><div>${ref(c.after)}</div></div></section>
      <div class="completion-flow"><article class="flow-node proposal"><span class="step-label">模型提出请求</span><strong>${ref(v.proposal_label)}</strong><p>${ref(v.proposal_detail)}</p></article><div class="not-yet">${ref(v.not_success_yet_label)}</div><article class="flow-node verify"><span class="step-label">预先声明的验收标准</span>${v.criteria.map(x=>`<div class="criterion"><span>${ref(x,x.id,'验收标准来源')}</span><b>${ref(x,x.result,'结果来源')}</b></div>`).join('')}</article><article class="flow-node accepted"><span class="step-label">持久化验收结果</span><strong>${ref(v.durable_verification_status)}</strong><small>${ref(v.supporting_line)}</small></article><div class="sequence">${completionEvents.map(e=>`<span class="event">${ref(e,e.event_number,'已记录事件位置')}<b>${ref(e,e.label,'事件来源')}</b></span>`).join('')}</div><article class="flow-node succeeded"><span class="step-label">最终任务状态</span><strong>${ref(v.terminal_task_state)}</strong><div class="verified-chip">${ref(f.completion_label)}</div></article></div>
      <section class="panel artifact-proof"><div><span class="panel-kicker">交付物完整性</span><strong>${ref(a.path)}</strong><small>交付物类别（演示标签）${ref(a.type)} · ${ref(a.status)} · ${ref(a.size_bytes,a.size_bytes.display_value)} · 已记录摘要与独立重算结果</small></div><div class="hash-compare"><span>${ref(a.recorded_sha256,undefined,'已记录的 SHA-256 摘要')}</span><span>${ref(a.recomputed_sha256,undefined,'重新计算的 SHA-256 摘要')}</span></div><b class="state-chip success">${ref(a.digest_result)}</b></section>
      <section class="panel retained-example"><div class="retained-label">单独保留的确定性示例 · 不属于成功运行</div><h2>${ref(neg.scenario)}</h2><p>验收结果：${ref(neg.verifier_result)}</p><small>${ref(neg.qualification)}</small></section>
      <section class="hook"><p>${ref(v.memory_hook)}</p><span>${ref(v.supporting_line)}</span></section>`;
  }
  function scene3(d) {
    const r=d.facts.recovery;
    const states=r.states;
    const path=states.map(s=>`<div class="recovery-step"><strong>${ref(s,s.label,'恢复状态来源')}<small>${ref(s.description)}</small></strong></div>`).join('<span class="flow-arrow" aria-hidden="true">→</span>');
    const branches=r.outcomes.map(s=>`<article class="branch"><span class="branch-node">${ref(s,s.label,'分支状态来源')}</span><p>${ref(s.description)}</p></article>`).join('');
    return `${header('场景 03 / 动作恢复','先核对事实，再决定下一步。',ref(r.reconciliation))}
      <div class="qualification">${ref(r.evidence_level, '限定条件下的运行时／故障窗口测试证据——不属于成功实证','资格说明来源')}</div>
      <section class="panel recovery-path"><div class="panel-head"><span class="panel-kicker">已测试窗口中的状态流转</span><span class="warning-chip">${ref(r.takeaway)}</span></div><div class="path-row">${path}</div><p class="reconcile">${ref(r.reconciliation)}</p><small>${ref(r.explicitly_not_claimed)}</small></section>
      <section class="branch-grid">${branches}</section>
      <div class="recovery-foot"><section class="panel fault-summary"><span class="panel-kicker">保留的故障窗口测试摘要</span><strong>${ref(r.fault_matrix_summary)}</strong></section><section class="panel limitation">${ref(r.raw_output_review_limitation)}</section></div>
      <p class="timeout-hook">${ref(r.takeaway)} <span>${ref(r.supporting_line)}</span></p>`;
  }
  function scene4(d) {
    const c=d.facts.comparison;
    const stages=(items, type)=>items.map((s,i)=>`<div class="stage"><span>${String(i+1).padStart(2,'0')}</span><strong>${escapeHTML(zh(s))}</strong></div>${i<items.length-1?'<i class="stage-arrow" aria-hidden="true">›</i>':''}`).join('');
    return `${header('场景 04 / 职责模型','两种流程，平实对照。','说明性示意图，并非对比实验。')}
      <div class="compare-grid"><section class="panel compare-lane"><div class="lane-head"><span class="panel-kicker">通用流程</span><h2>${ref(c.generic_agent_title)}</h2></div><div class="stages">${stages(c.generic_agent_stages.value)}</div>${ref(c.generic_agent_stages,undefined,'流程来源')}</section><section class="panel compare-lane astron-lane"><div class="lane-head"><span class="panel-kicker">明确的执行职责</span><h2>${ref(c.astron_title)}</h2></div><div class="stages">${stages(c.astron_stages.value)}</div>${ref(c.astron_stages,undefined,'流程来源')}</section></div>
      <blockquote class="neutral-caption">${ref(c.caption)}</blockquote><p class="neutral-note">${ref(c.disclaimer)}</p>`;
  }
  function indexPage() {
    return `${header('产品流程演示','Astron 执行治理流程','动作授权、任务验收、异常恢复与执行职责。')}
      <div class="index-callout"><p>可离线浏览的静态流程演示，不会连接模型服务或启动实时运行时。</p></div><div class="index-grid">${screens.map(([file,label],i)=>`<a class="index-card" href="${base}${file}"><span class="card-num">0${i+1}</span><strong>${label.replace(/^\d+ /,'')}</strong><span>${['展示动作授权、受限执行与持久记录','展示验收标准如何确认任务完成','展示结果未知时的核对与恢复流程','展示 Agent 与运行时各自承担的职责'][i]}</span><b>打开页面 →</b></a>`).join('')}</div><section class="panel preview-instruction"><span class="panel-kicker">本地预览</span><p>在项目的 <code>competition</code> 目录运行 <code>python3 -m http.server 8000</code>，然后访问 <code>http://localhost:8000/visual/</code></p><small>页面资源与回放数据均来自本地文件，无需额外构建或外部服务。</small></section>`;
  }
  Promise.all([fetch('DEMO_REPLAY_DATA_V1.json'),fetch('../demo_evidence/06_EVIDENCE_TO_SCREEN_MAP.json')]).then(rs=>{if(rs.some(r=>!r.ok))throw new Error('本地回放数据或证据映射文件无法读取。');return Promise.all(rs.map(r=>r.json()));}).then(([d,map])=>{
    window.astronEvidenceMap = map;
    const render={0:indexPage,1:scene1,2:scene2,3:scene3,4:scene4}[screen] || indexPage;
    app.innerHTML=render(d);
  }).catch(()=>{app.innerHTML=`<section class="panel error-panel"><h1>无法载入回放数据</h1><p>本地回放数据或证据映射文件无法读取。</p><p>请从 competition 目录启动本地预览服务，并确认回放数据与映射文件可读取。</p></section>`;});
})();
