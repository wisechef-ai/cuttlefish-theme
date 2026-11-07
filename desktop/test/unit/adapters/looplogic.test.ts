// Unit contract of the budgeted-loop decision logic (adapters lane): exactly the domain's
// motionPlan as an idleWhen, with a draw-clock that blooms every real state change even
// after a long park, and never blooms the initial sight.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { drawClock, idleSince, noteStateChange, type LoopClock } from '../../../src/adapters/looplogic.ts'
import { applyFeed, initialView, type CfView } from '../../../src/adapters/view.ts'
import { wantsFrame } from '../../../src/adapters/looplogic.ts'

const clock = (): LoopClock => ({ lastNow: 0, changeAt: null, pending: false })
const view = (): CfView => initialView({ width: 1200, height: 800, ground: '#141416', reducedMotion: false })
const busy = (v: CfView): boolean =>
  applyFeed(v, { kind: 'state', t: 0, session: 'a', payload: { gateway: 'open', busy: true, focused_session_id: 'a', focused_stored_session_id: 'SA' } })

test('loop: parked at rest from the very first sight (no bloom for the initial state)', () => {
  const c = clock()
  const v = view()
  drawClock(c, 100)
  assert.equal(wantsFrame(v, idleSince(c)), false, 'resting + still parks the loop')
})

test('loop: a state change parks nothing — it blooms from the first frame after any gap', () => {
  const c = clock()
  drawClock(c, 0)
  drawClock(c, 600_000)                       // parked ten minutes
  noteStateChange(c)
  assert.equal(idleSince(c), 0, 'the change is pending until a frame sees it')
  assert.equal(drawClock(c, 600_125), 0, 'the first draw after the change starts the bloom')
  assert.ok(drawClock(c, 600_250) > 0)
  assert.ok(drawClock(c, 603_000) >= 2400, 'the bloom tail')
  noteStateChange(c)
  drawClock(c, 700_000)
  assert.equal(c.changeAt, 700_000, 'a late change re-anchors at its own first frame')
})

test('loop: idleWhen follows motionPlan across states, motion and reduced motion', () => {
  const v = view()
  const c = clock()
  drawClock(c, 5000)
  const idle = (): boolean => !wantsFrame(v, idleSince(c))
  assert.equal(idle(), true, 'resting')
  assert.equal(busy(v), true)
  assert.equal(idle(), false, 'working clouds run')
  v.reducedMotion = true
  assert.equal(idle(), true, 'reduced motion parks even while working')
  v.reducedMotion = false
  v.motion = 'off'
  assert.equal(idle(), true, 'motion off from config parks')
  v.motion = 'alive'
  assert.equal(idle(), false, 'alive twinkles even at rest')
})

test('loop: the bloom itself animates at rest until it settles', () => {
  const v = view()
  const c = clock()
  noteStateChange(c)
  drawClock(c, 0)
  assert.equal(wantsFrame(v, idleSince(c)), true, 'a fresh change blooms')
  drawClock(c, 3000)
  assert.equal(wantsFrame(v, idleSince(c)), false, 'settled after BLOOM_MS')
})
