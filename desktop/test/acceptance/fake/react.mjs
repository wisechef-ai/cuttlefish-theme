// ACCEPTANCE CONTRACT — a FAKE `react` / `react/jsx-runtime` (locked).
// Elements are plain objects. `expand(node)` runs function components with a minimal hook runtime so the tests can
// read what a slot WOULD render (its attributes and children) and run its effects like a mount would.
export const Fragment = Symbol.for('fake.fragment')

export function jsx(type, props, key) { return { $$fake: true, type, props: props ?? {}, key: key ?? null } }
export const jsxs = jsx
export function createElement(type, props, ...children) {
  const p = { ...(props ?? {}) }
  if (children.length) p.children = children.length === 1 ? children[0] : children
  return jsx(type, p, p.key)
}

let frame = null
const slot = () => {
  if (!frame) throw new Error('fake react: hook called outside a component')
  const i = frame.i++
  return [frame.slots, i]
}
export function useState(init) {
  const [slots, i] = slot()
  if (!(i in slots)) slots[i] = typeof init === 'function' ? init() : init
  return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v }]
}
export const useReducer = (r, init) => { const [s, set] = useState(init); return [s, a => set(r(s, a))] }
export function useRef(init) { const [slots, i] = slot(); if (!(i in slots)) slots[i] = { current: init }; return slots[i] }
export function useMemo(fn) { const [slots, i] = slot(); if (!(i in slots)) slots[i] = fn(); return slots[i] }
export const useCallback = fn => useMemo(() => fn)
export function useEffect(fn) { if (!frame) throw new Error('fake react: hook outside a component'); frame.effects.push(fn) }
export const useLayoutEffect = useEffect
export const useSyncExternalStore = (_subscribe, get) => get()
export const useId = () => 'fake-id'
export const memo = c => c
export const forwardRef = c => props => c(props, null)
export const createContext = v => ({ Provider: p => p.children, _v: v })
export const useContext = c => c._v

/** Expand a node: call function components (fresh hook state), collect effects. Returns { tree, effects }. */
export function expand(node, state = { effects: [] }) {
  if (node === null || node === undefined || typeof node === 'boolean') return { tree: null, effects: state.effects }
  if (Array.isArray(node)) return { tree: node.map(n => expand(n, state).tree), effects: state.effects }
  if (typeof node !== 'object' || !node.$$fake) return { tree: node, effects: state.effects }
  if (typeof node.type === 'function') {
    const saved = frame
    frame = { i: 0, slots: [], effects: state.effects }
    let out
    try { out = node.type(node.props) } finally { frame = saved }
    return expand(out, state)
  }
  const children = node.props.children === undefined ? undefined : expand(node.props.children, state).tree
  return { tree: { type: node.type, props: { ...node.props, children } }, effects: state.effects }
}

/** Every host element in a tree, depth-first. */
export function walk(tree, out = []) {
  if (tree === null || tree === undefined) return out
  if (Array.isArray(tree)) { for (const t of tree) walk(t, out); return out }
  if (typeof tree !== 'object') return out
  out.push(tree)
  walk(tree.props?.children, out)
  return out
}

const React = { Fragment, createElement, useState, useReducer, useRef, useMemo, useCallback, useEffect, useLayoutEffect,
  useSyncExternalStore, useId, memo, forwardRef, createContext, useContext }
export default React
