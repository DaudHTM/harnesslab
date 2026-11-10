import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Experiment = { id: string; name: string; created: number };
type Run = { id: string; task_path: string; config: string; status: string; attempt: number; result: string | null };
type Event = { seq: number; attempt: number; kind: string; created: number; data: Record<string, unknown> };
type Comparison = { harness: string; model: string; config_hash: string; scripted_fixture: boolean; total: number; completed: number; solved: number; success_rate: number | null; cost_usd: number; median_seconds: number | null; infrastructure_errors: number };
type Detail = { runs: Run[]; comparison: Comparison[] };

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch('/api' + url, options);
  if (!r.ok) throw new Error(`Request failed (${r.status}): ${await r.text()}`);
  return r.json() as Promise<T>;
}

function App() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [patch, setPatch] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [tab, setTab] = useState<'trace' | 'patch'>('trace');

  useEffect(() => {
    let current = true;
    const load = () => api<Experiment[]>('/experiments').then(x => { if (current) setExperiments(x); }).catch(e => { if (current) setError(String(e)); });
    void load(); const timer = setInterval(load, 3000);
    return () => { current = false; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let current = true;
    const load = () => api<Detail>(`/experiments/${selected}`).then(x => { if (current) setDetail(x); }).catch(e => { if (current) setError(String(e)); });
    setDetail(null); setActiveRun(null); void load(); const timer = setInterval(load, 1500);
    return () => { current = false; clearInterval(timer); };
  }, [selected]);

  const runId = activeRun?.id;
  useEffect(() => {
    setEvents([]); setPatch('');
    if (!runId) return;
    let current = true;
    const stream = new EventSource(`/api/runs/${runId}/stream`);
    stream.onmessage = message => { const event: Event = JSON.parse(message.data); if (current) setEvents(old => old.some(x => x.seq === event.seq) ? old : [...old, event]); };
    stream.onerror = () => {
      void api<Run>(`/runs/${runId}`).then(run => {
        if (current && !['queued', 'running'].includes(run.status)) stream.close();
      }).catch(() => { /* EventSource retries transient disconnects automatically. */ });
    };
    const loadPatch = () => api<{ patch: string }>(`/runs/${runId}/patch`).then(x => { if (current) setPatch(x.patch); }).catch(() => {});
    void loadPatch(); const timer = setInterval(loadPatch, 2000);
    return () => { current = false; stream.close(); clearInterval(timer); };
  }, [runId]);

  async function createDemo() {
    setPending(true); setError('');
    try {
      const result = await api<{ id: string }>('/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Normalization · fixture comparison', tasks: ['tag-normalization'], configs: [{ name: 'baseline' }, { name: 'resilient' }] }) });
      setExperiments(await api<Experiment[]>('/experiments')); setSelected(result.id);
    } catch (e) { setError(String(e)); } finally { setPending(false); }
  }
  const completed = detail?.runs.filter(r => !['queued', 'running'].includes(r.status)).length ?? 0;
  const solved = detail?.runs.filter(r => r.status === 'solved').length ?? 0;
  const currentRun = detail?.runs.find(r => r.id === runId) ?? activeRun;

  return <div className="layout">
    <aside><a className="brand" href="/">h<span>▧</span> HarnessLab</a><div className="workspace">ENGINEERING WORKSPACE</div><div className="nav active">◉ &nbsp; Experiments</div><div className="aside-label">RECENT EXPERIMENTS</div><nav aria-label="Experiments">{experiments.map(e => <button key={e.id} className={`experiment ${e.id === selected ? 'chosen' : ''}`} onClick={() => setSelected(e.id)}>{e.name}<small>{new Date(e.created * 1000).toLocaleDateString()}</small></button>)}</nav><div className="aside-bottom"><span className="dot"/> Local environment<br/><small>Curated tasks · isolated evaluation</small></div></aside>
    <main><header><span>Workspace <span className="muted">/</span> Experiments</span><span className="version">HARNESSLAB <b>0.1</b></span></header>
      <div className="heading"><div><div className="eyebrow">MEASURE. INSPECT. IMPROVE.</div><h1>Agent reliability, observed.</h1><p>Every tool call. Every patch. Evidence behind every result.</p></div><button className="primary" disabled={pending} onClick={createDemo}>{pending ? 'Creating…' : '+ New demo experiment'}</button></div>
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      <div className="notice"><span>ⓘ</span><div><b>Honest by default.</b> Demo runs use a scripted model fixture. They verify the pipeline and do not measure AI capability. Start a worker to process queued runs.</div></div>
      <section className="metrics" aria-label="Experiment metrics">{[['TOTAL RUNS', detail?.runs.length ?? '—'], ['COMPLETED', completed], ['SOLVED', solved], ['RECORDED COST', `$${(detail?.comparison.reduce((s, c) => s + c.cost_usd, 0) ?? 0).toFixed(4)}`]].map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{label === 'SOLVED' ? 'Independently graded patches' : label === 'RECORDED COST' ? 'Includes failed attempts' : 'Selected experiment'}</small></div>)}</section>
      {!selected ? <section className="empty"><div className="empty-icon">⌁</div><h2>Start with an experiment.</h2><p>Create a demo or select a previous experiment to compare harnesses and inspect execution traces.</p><button className="primary" onClick={createDemo} disabled={pending}>Create a demo experiment →</button></section> : <>
        <section className="panel"><div className="panel-title"><h2>Harness comparison</h2><a href={`/api/experiments/${selected}/export`} download="experiment.json">Export JSON ↗</a></div><div className="table-wrap"><table><thead><tr><th>HARNESS / MODEL</th><th>PROGRESS</th><th>SUCCESS RATE</th><th>MEDIAN TIME</th><th>INFRA ERRORS</th></tr></thead><tbody>{detail?.comparison.map(c => <tr key={c.config_hash}><td><b>{c.harness}</b><small>{c.model} {c.scripted_fixture && '· scripted fixture'}</small></td><td>{c.completed} / {c.total}</td><td>{c.success_rate === null ? '—' : `${(c.success_rate * 100).toFixed(0)}%`}</td><td>{c.median_seconds === null ? '—' : `${c.median_seconds.toFixed(2)}s`}</td><td>{c.infrastructure_errors}</td></tr>)}</tbody></table></div></section>
        <section className="panel"><div className="panel-title"><h2>Execution runs</h2><span className="muted">Select a run to inspect</span></div><div className="table-wrap"><table><thead><tr><th>TASK</th><th>HARNESS</th><th>STATUS</th><th>ATTEMPTS</th><th/></tr></thead><tbody>{detail?.runs.map(r => <tr key={r.id} className={runId === r.id ? 'selected-row' : ''}><td><b>{r.task_path.split('/').at(-1)?.replace('.json', '')}</b><small>{r.id.slice(0, 12)}</small></td><td>{JSON.parse(r.config).name}</td><td><span className={`status ${r.status}`}>{r.status.replaceAll('_', ' ')}</span></td><td>{r.attempt}</td><td><button className="text-button" onClick={() => { setActiveRun(r); setTab('trace'); }}>Inspect →</button></td></tr>)}</tbody></table></div></section>
        {currentRun && <section className="panel"><div className="panel-title"><h2>Run <code>{currentRun.id.slice(0, 12)}</code></h2>{['queued', 'running'].includes(currentRun.status) && <button className="text-button danger" onClick={() => api(`/runs/${currentRun.id}/cancel`, { method: 'POST' }).catch(e => setError(String(e)))}>Cancel run</button>}</div><div className="tabs"><button aria-pressed={tab === 'trace'} onClick={() => setTab('trace')}>Execution trace <span>{events.length}</span></button><button aria-pressed={tab === 'patch'} onClick={() => setTab('patch')}>Patch diff</button></div>{tab === 'trace' ? <ol className="timeline">{events.length === 0 && <p className="muted">Waiting for worker events…</p>}{events.map(e => <li key={e.seq}><span className="event-marker"/><details><summary><b>{e.kind.replaceAll('_', ' ')}</b><small>#{e.seq} · attempt {e.attempt} · {new Date(e.created * 1000).toLocaleTimeString()}</small></summary><pre>{JSON.stringify(e.data, null, 2)}</pre></details></li>)}</ol> : <pre className="diff">{patch || 'No patch available yet.'}</pre>}</section>}
      </>}
      <footer>Reproducible environments. Independent grading. No hidden success claims.</footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
