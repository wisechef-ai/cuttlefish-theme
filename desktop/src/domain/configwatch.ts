// C5: settings apply without a restart — the desktop watches the config file's mtime (an opaque
// version token: a number of ms, or a string like 'ms:rev') and refetches exactly when it CHANGES.
// An unreadable mtime (null) keeps the last settings, never resets them; the first sight fetches.

export interface ConfigWatch {
  /** false until the first mtime has been seen (the first sight always fetches). */
  seen: boolean
  /** The last token fetched, exactly as observed (numbers and strings compare by their text). */
  mtime: number | string | null
}

export function initialConfigWatch(): ConfigWatch {
  return { seen: false, mtime: null }
}

const tokenOf = (m: number | string | null | undefined): string | null => {
  if (typeof m === 'number' && Number.isFinite(m)) return String(m)
  if (typeof m === 'string' && m.length > 0) return m
  return null
}

/** Decide whether to refetch the settings. Pure: returns the next watch, never mutates. */
export function configPlan(watch: ConfigWatch, mtime: number | string | null):
  { refetch: boolean; next: ConfigWatch } {
  const token = tokenOf(mtime)
  if (token === null) return { refetch: false, next: watch }
  if (watch.seen && token === tokenOf(watch.mtime)) return { refetch: false, next: watch }
  return { refetch: true, next: { seen: true, mtime: typeof mtime === 'number' ? mtime : token } }
}
