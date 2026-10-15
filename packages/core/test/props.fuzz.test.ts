// cf2909 P2-PROPS (card t_c7ef96e9): 7 fuzz/property invariants over the core source and BOTH
// committed bundles, ≥ 1000 runs each, seed printed on failure. These assert CONTRACT.md §1–§3
// invariants — they never re-implement the reducers, they observe them.
// Each test names its red proof (see the card summary): the planted bug that made it fail.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';
import {
  hookInitial, hookReduce, hookResolve, STALE_S,
  allocate, hueOfSlot, paint, frameStep,
  replayJson as sourceReplayJson,
} from '../index.ts';
import type { HookEvent, HookModel } from '../index.ts';

const repoFile = (rel: string) => new URL(`../../../${rel}`, import.meta.url);
const DESKTOP = 'desktop/core.bundle.js';
const TUI = 'tui/core.bundle.mjs';
const bundles = async () => ({
  desktop: await import(repoFile(DESKTOP).href),
  tui: await import(repoFile(TUI).href),
});

/** Run one property; on failure print the seed (fast-check's counterexample carries it too) and rethrow. */
function prop(name: string, seed: number, p: fc.IAsyncProperty<unknown> | fc.IProperty<unknown>, params: fc.Parameters<unknown> = {}): Promise<void> | void {
  const cfg = { seed, numRuns: 1000, ...params };
  try {
    const r = fc.assert(p as never, cfg);
    if (r instanceof Promise) return r.catch((e: unknown) => { console.error(`PROPERTY FAILED [${name}] seed=${seed}`); throw e; });
    return;
  } catch (e) {
    console.error(`PROPERTY FAILED [${name}] seed=${seed}`);
    throw e;
  }
}

// ---- arbitrary builders -----------------------------------------------------------------------------------

const HOOK_KINDS = ['on_session_reset', 'on_session_start', 'pre_llm_call', 'post_llm_call', 'on_session_end',
  'on_session_finalize', 'pre_tool_call', 'post_tool_call', 'pre_approval_request', 'post_approval_response',
  'api_request_error', 'pre_verify', 'heartbeat', 'pid_dead', 'binding', 'on_stream_delta'] as const;

/** One random hook event: small id pools so clarify/approval opens and closes actually collide. */
const hookEventArb = fc.record({
  dt: fc.constantFrom(0, 0.1, 0.5, 1, 4, 6, 19.9, 21, 40),
  kind: fc.constantFrom(...HOOK_KINDS),
  tool: fc.constantFrom('clarify', 'terminal'),
  id: fc.constantFrom('c1', 'c2', 'a1', 'a2'),
  flag: fc.boolean(),
});

const hookSeqArb = fc.array(hookEventArb, { minLength: 1, maxLength: 60 })
  .map(evs => {
    let t = 0;
    return evs.map(e => {
      t += e.dt;
      const payload: Record<string, unknown> = { tool_name: e.tool, tool_call_id: e.id, completed: e.flag, bound: e.flag, session_key: 'sk', pattern_key: 'pk' };
      return { t, kind: e.kind, payload } as HookEvent;
    });
  });

/** Deterministic PRNG for test-local shuffles (the property stays fast-check's; this only permutes inputs). */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle<T>(xs: readonly T[], rnd: () => number): T[] {
  const out = [...xs];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

const pixelSig = (px: Uint8ClampedArray): string => {
  let h = 0x811c9dc5;
  for (let i = 0; i < px.length; i++) h = Math.imul(h ^ px[i], 0x01000193) >>> 0;
  return `${px.length}:${h}`;
};

const samePixels = (a: Uint8ClampedArray, b: Uint8ClampedArray): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
};

// ---- 1. bundle parity: byte-identical replay() canonical output on random sequences ----------------------

test('P1 (1000 runs): both bundles give byte-identical replay() output on random hook-event sequences [red: desktop bundle STALE_S 20→21]', async () => {
  const { desktop, tui } = await bundles();
  const seqArb = fc.array(hookEventArb, { minLength: 1, maxLength: 40 })
    .map(evs => {
      let t = 0;
      const rows: object[] = [{ v: 1, src: 'meta', kind: 'trace', name: 'props-hook', host: 'tui' }];
      for (const e of evs) {
        t += e.dt;
        rows.push({ v: 1, t, src: e.kind === 'heartbeat' || e.kind === 'pid_dead' ? 'liveness' : 'hook',
          profile: e.flag ? 'A' : 'B', session: 's', lineage_root: e.flag ? 'r1' : 'r2', kind: e.kind,
          payload: { tool_name: e.tool, tool_call_id: e.id, completed: e.flag, bound: e.flag } });
      }
      return { rows, step: eStep(evs.length) };
    });
  // keep step positive and varied
  function eStep(n: number): number { return [0.25, 0.5, 1, 3][n % 4]; }
  await prop('P1-hook', 290911, fc.property(seqArb, ({ rows, step }) => {
    const want = sourceReplayJson(rows, { stepS: step });
    assert.equal(desktop.replayJson(rows, { stepS: step }), want, 'desktop bundle replayJson diverged from source');
    assert.equal(tui.replayJson(rows, { stepS: step }), want, 'tui bundle replayJson diverged from source');
  }));
});

test('P1b (1000 runs): both bundles give byte-identical replay() output on random desktop sequences [red: desktop bundle STALE_S 20→21]', async () => {
  const { desktop, tui } = await bundles();
  const deskArb = fc.array(fc.record({
    dt: fc.constantFrom(0, 0, 0.3, 1, 7, 30),
    kind: fc.constantFrom('state', 'session.info', 'message.start', 'message.complete', 'dot'),
    rt: fc.constantFrom('rt1', 'rt2', 'rt3'),
    gateway: fc.constantFrom('open', 'closed', 'connecting'),
    busy: fc.boolean(),
    label: fc.constantFrom('Session running', 'Needs your input', '', 'Background task running'),
    status: fc.constantFrom('error', 'complete'),
  }), { minLength: 1, maxLength: 40 }).map(evs => {
    let t = 0;
    const rows: object[] = [{ v: 1, src: 'meta', kind: 'trace', name: 'props-desktop', host: 'desktop' }];
    for (const e of evs) {
      t += e.dt;
      const stored = `st-${e.rt}`;
      rows.push(e.kind === 'dot'
        ? { v: 1, t, src: 'desktop.dot', profile: 'A', session: stored, lineage_root: null, kind: 'dot', payload: { label: e.label } }
        : { v: 1, t, src: e.kind === 'state' ? 'desktop.state' : 'desktop.event', profile: 'A',
            session: e.kind === 'state' ? null : e.rt, lineage_root: null, kind: e.kind,
            payload: e.kind === 'state' ? { gateway: e.gateway, busyBySession: { [e.rt]: e.busy } }
              : e.kind === 'session.info' ? { stored_session_id: stored } : { status: e.status } });
    }
    return rows;
  });
  await prop('P1-desktop', 290912, fc.property(deskArb, fc.constantFrom(0.5, 1, 2), (rows, step) => {
    const want = sourceReplayJson(rows, { stepS: step });
    assert.equal(desktop.replayJson(rows, { stepS: step }), want, 'desktop bundle replayJson diverged from source');
    assert.equal(tui.replayJson(rows, { stepS: step }), want, 'tui bundle replayJson diverged from source');
  }));
});

// ---- 2. finalize / pid_dead latch: 'unknown' until the ONE reviving hook ----------------------------------

test('P2 (1000 runs): on_session_finalize ⇒ unknown until pre_llm_call/on_session_reset; pid_dead ⇒ unknown until heartbeat/on_session_reset [red: finalize case drops `finalized: true`]', async () => {
  await prop('P2', 290913, fc.property(hookSeqArb, seq => {
    let model: HookModel = hookInitial();
    let latch: 'finalize' | 'pid_dead' | null = null;
    for (const ev of seq) {
      model = hookReduce(model, ev);
      if (ev.kind === 'on_session_finalize') latch = 'finalize';            // survives every later hook except the two revivers
      else if (ev.kind === 'pid_dead') latch = latch ?? 'pid_dead';
      else if (ev.kind === 'pre_llm_call' || ev.kind === 'on_session_reset') latch = null;
      else if (ev.kind === 'heartbeat' && latch === 'pid_dead') latch = null;   // a heartbeat revives pid_dead only
      if (latch !== null) assert.equal(hookResolve(model, ev.t), 'unknown',
        `after ${latch}, a ${ev.kind} event must not revive the session (got non-unknown at t=${ev.t})`);
    }
  }));
});

// ---- 3. no event for > 20 s ⇒ 'unknown' --------------------------------------------------------------------

test('P3 (1000 runs): silence strictly greater than 20 s resolves to unknown at the sampled instant [red: stale comparison scaled by 100]', async () => {
  await prop('P3', 290914, fc.property(hookSeqArb, seq => {
    let model: HookModel = hookInitial();
    let prev: { t: number; model: HookModel } | null = null;
    for (const ev of seq) {
      model = hookReduce(model, ev);
      if (prev !== null && ev.t - prev.t > STALE_S) {
        const sample = prev.t + STALE_S + 0.5;
        assert.equal(hookResolve(prev.model, sample), 'unknown',
          `a session silent from t=${prev.t} to t=${ev.t} must be unknown when sampled at t=${sample}`);
      }
      prev = { t: ev.t, model };
    }
    if (prev !== null && prev.model.last_seen !== null) {
      assert.equal(hookResolve(prev.model, prev.t + STALE_S + 0.5), 'unknown', 'the tail after the last event must go unknown');
    }
  }));
});

// ---- 4. live + bound: 'needs-you' iff the opened-minus-closed prompt set is non-empty ----------------------

test('P4 (1000 runs): for a live, bound session, needs-you ⇔ pending (opened-minus-closed clarify/approval keys) is non-empty [red: pending check inverted]', async () => {
  await prop('P4', 290915, fc.property(hookSeqArb, seq => {
    let model: HookModel = hookInitial();
    for (const ev of seq) {
      model = hookReduce(model, ev);
      const live = model.last_seen !== null && !model.finalized && model.pid_alive !== false && model.bound
        && ev.t - model.last_seen <= STALE_S;
      if (!live) continue;
      const pending = model.pending.length > 0;
      assert.equal(hookResolve(model, ev.t) === 'needs-you', pending,
        `needs-you must equal pending-non-empty (pending=[${model.pending.join(', ')}] after ${ev.kind} at t=${ev.t})`);
    }
  }));
});

// ---- 5. a turn ended with completed:true and no pending prompt never resolves needs-you ---------------------

const PROMPTLESS_TAIL = ['post_llm_call', 'on_session_end', 'on_session_start', 'post_tool_call', 'post_approval_response',
  'pre_verify', 'heartbeat', 'on_stream_delta', 'binding'] as const;

test('P5 (1000 runs): on_session_end{completed:true} + promptless tail never resolves needs-you ("turn ended ≠ needs you") [red: end hook stops clearing pending]', async () => {
  const tailArb = fc.array(fc.record({
    dt: fc.constantFrom(0, 0.2, 1, 5),
    kind: fc.constantFrom(...PROMPTLESS_TAIL),
    tool: fc.constantFrom('clarify', 'terminal'),
    id: fc.constantFrom('c1', 'c2', 'a1', 'a2'),
    flag: fc.boolean(),
  }), { minLength: 0, maxLength: 20 });
  await prop('P5', 290916, fc.property(hookSeqArb, tailArb, (seq, tail) => {
    let model: HookModel = hookInitial();
    for (const ev of seq) model = hookReduce(model, ev);
    const endT = seq[seq.length - 1].t + 0.5;
    model = hookReduce(model, { t: endT, kind: 'on_session_end', payload: { completed: true } });
    assert.notEqual(hookResolve(model, endT), 'needs-you', 'the instant the turn ends is never needs-you');
    let t = endT;
    for (const e of tail) {
      t += e.dt;
      model = hookReduce(model, { t, kind: e.kind, payload: { tool_name: e.tool, tool_call_id: e.id, bound: e.flag } });
      assert.notEqual(hookResolve(model, t), 'needs-you', `turn ended: a ${e.kind} event must not bring back needs-you (t=${t})`);
    }
  }));
});

// ---- 6. identity: never take a peer-held slot while a free one exists; stable under permutation/duplication --

test('P6 (1000 runs): allocate() never returns a peer-held slot while a free one exists, and is invariant under permutation and duplication of peers [red: the held-slot set is built empty — occupancy dropped]', async () => {
  await prop('P6', 290917, fc.property(
    fc.string({ minLength: 1, maxLength: 24 }).map(s => `lineage-${s}`),
    fc.array(fc.nat(19), { minLength: 0, maxLength: 24 }),
    (root, peers) => {
      const a = allocate(root, peers);
      const held = new Set(peers);
      assert.ok(Number.isInteger(a.slot) && a.slot >= 0 && a.slot < 20, 'slot is an integer in 0..19');
      assert.equal(a.hue_deg, hueOfSlot(a.slot), 'hue_deg is the hue of the returned slot');
      if (held.size < 20) {
        assert.ok(!held.has(a.slot), `slot ${a.slot} is held by a peer yet was returned while free slots exist (peers=${peers})`);
        assert.equal(a.crowded, false, 'crowded is never true while a free slot exists');
      } else {
        assert.equal(a.crowded, true, 'all 20 slots held ⇒ crowded is surfaced, never hidden');
      }
      const rnd = mulberry32(a.slot * 7919 + root.length);
      const permuted = shuffle(peers, rnd);
      assert.deepEqual(allocate(root, permuted), a, 'permuting peers must not change the allocation');
      assert.deepEqual(allocate(root, [...peers, ...peers]), a, 'duplicating peers must not change the allocation');
      assert.deepEqual(allocate(root, shuffle([...peers, ...permuted], rnd)), a, 'duplication + permutation must not change the allocation');
    },
  ));
});

// ---- 7. pattern: non-working looks are static; working is static under reducedMotion and moves otherwise -----

const STATIC_LOOKS = ['idle', 'review', 'needs-you', 'fault', 'unknown'] as const;
const SCALES = [
  { scale: 'XL', w: 96, h: 32 },
  { scale: 'M', w: 28, h: 3 },
  { scale: 'S', w: 4, h: 2 },      // the desktop swatch
  { scale: 'S', w: 14, h: 2 },
] as const;
const T_STATIC = 37.25;            // seconds; the card's probe instant (frameStep = 149)

test('P7 (1000 runs): every non-working look (and working under reducedMotion) is byte-identical at t=0 and t=37.25 [red: the paint seed drifts with the frame step — every look flickers]', async () => {
  const surfArb = fc.record({
    hue: fc.float({ min: 110, max: 340, noNaN: true }),
    look: fc.constantFrom(...STATIC_LOOKS),
    degraded: fc.boolean(),
    reduced: fc.boolean(),
    surface: fc.constantFrom(...SCALES),
    name: fc.constantFrom('', 's1', 'a longer session name'),
    alarm: fc.constantFrom(null, 'clarify?', 'API 401'),
  });
  await prop('P7-static', 290918, fc.property(surfArb, s => {
    const base = {
      scale: s.surface.scale, w: s.surface.w, h: s.surface.h,
      hueDeg: s.degraded ? null : s.hue, name: s.name, alarmText: s.alarm, reducedMotion: s.reduced,
    };
    const at = (t: number) => paint({ ...base, look: s.look, step: frameStep(t) });
    const a = at(0), b = at(T_STATIC);
    assert.ok(samePixels(a.pixels, b.pixels), `${s.look} at ${s.surface.scale} ${s.surface.w}x${s.surface.h} must be static (pixels differ between t=0 and t=${T_STATIC})`);
    assert.deepEqual(a.text, b.text, 'text must be static too');
    // working + reducedMotion is static as well
    const wa = paint({ ...base, look: 'working', step: 0 });
    const wb = paint({ ...base, look: 'working', step: frameStep(T_STATIC), reducedMotion: true });
    assert.ok(samePixels(wa.pixels, wb.pixels), 'working under reducedMotion must be static');
  }));
});

test('P7b (1000 runs): working moves at every scale incl. the S 4x2 swatch — ≥ 3 distinct frames in 12 steps [red: the cloud band stops drifting (− step removed)]', async () => {
  await prop('P7-move', 290919, fc.property(
    fc.float({ min: 110, max: 340, noNaN: true }),
    fc.constantFrom(...SCALES),
    (hue, surface) => {
      const frames = new Set<string>();
      for (let step = 0; step < 12; step++) {
        frames.add(pixelSig(paint({ scale: surface.scale, w: surface.w, h: surface.h, look: 'working', hueDeg: hue, name: 's', alarmText: null, step, reducedMotion: false }).pixels));
      }
      assert.ok(frames.size >= 3, `working at ${surface.scale} ${surface.w}x${surface.h} must animate (got ${frames.size} distinct frames of 12)`);
    },
  ));
});
