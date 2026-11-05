// ACCEPTANCE CONTRACT — a FAKE @hermes/plugin-sdk for loading desktop/plugin.js in node (locked).
// Generated once by cf-lead from apps/desktop/src/sdk/{index,areas}.ts at Hermes v0.22.7 (190 runtime exports), then
// hand-modelled where a well-behaved cuttlefish plugin needs it. Everything else is a stub that THROWS when used, so
// a plugin relying on an unmodelled door fails loudly here instead of passing silently. The fake also records every
// call the tests make claims about (registrations, requests, loops, colour writes).
import { jsx } from './react.mjs'

export const calls = { requests: [], setColor: [], requestTheme: [], accent: [], loops: [], notify: [] }

// ---- atoms (nanostores-shaped) -------------------------------------------------------------------------------
export function atom(value) {
  const subs = new Set()
  return {
    get: () => value,
    set(v) { value = v; for (const s of [...subs]) s(v) },
    listen(fn) { subs.add(fn); return () => subs.delete(fn) },
    subscribe(fn) { subs.add(fn); fn(value); return () => subs.delete(fn) },
    get lc() { return subs.size },
  }
}
export function computed(deps, fn) {
  const list = Array.isArray(deps) ? deps : [deps]
  const out = atom(fn(...list.map(d => d.get())))
  for (const d of list) d.listen(() => out.set(fn(...list.map(x => x.get()))))
  return out
}
export const useValue = a => a.get()

// ---- host --------------------------------------------------------------------------------------------------
const listeners = new Map()
export const fake = {
  /** responder(method, params) → result (or throw) for host.request */
  responder: (method) => { throw new Error(`fake host.request: no responder for ${method}`) },
  emit(event) {
    for (const [type, fns] of listeners) if (type === '*' || type === event.type) for (const fn of [...fns]) fn(event)
  },
  listenerCount: () => [...listeners.values()].reduce((n, s) => n + s.size, 0),
  reset() {
    listeners.clear()
    for (const k of Object.keys(calls)) calls[k].length = 0
    fake.responder = (method) => { throw new Error(`fake host.request: no responder for ${method}`) }
    for (const [k, v] of Object.entries(INITIAL)) host.state[k].set(v)
  },
}
const INITIAL = {
  activeSessionId: null, focusedSessionId: null, focusedStoredSessionId: null, busyBySession: {}, gateway: 'open',
  busy: false, awaitingResponse: false, connectionId: null, cwd: '', focusedSessionOwner: null,
  focusedSessionProfile: 'default', focusedUsage: null, model: 'mock', profile: 'default', viewport: { width: 1200, height: 800 },
}
export const host = {
  state: Object.fromEntries(Object.entries(INITIAL).map(([k, v]) => [k, atom(v)])),
  request: async (method, params) => { calls.requests.push({ method, params }); return fake.responder(method, params) },
  onEvent(type, fn) {
    if (!listeners.has(type)) listeners.set(type, new Set())
    listeners.get(type).add(fn)
    return () => listeners.get(type)?.delete(fn)
  },
  notify: n => { calls.notify.push(n) },
  notifyError: n => { calls.notify.push(n) },
  sessions: {
    setColor: (id, c) => { calls.setColor.push([id, c]) },
    pin: unmodelled('host.sessions.pin'), reorder: unmodelled('host.sessions.reorder'),
    reorderPinned: unmodelled('host.sessions.reorderPinned'),
  },
  navigate: unmodelled('host.navigate'), logs: unmodelled('host.logs'), status: unmodelled('host.status'),
  restartGateway: unmodelled('host.restartGateway'),
}

// ---- createBudgetedLoop ---------------------------------------------------------------------------------------
export function createBudgetedLoop(draw, opts = {}) {
  const rec = { draw, opts, wakes: 0, disposed: false, draws: 0 }
  calls.loops.push(rec)
  return {
    wake() { if (!rec.disposed) rec.wakes++ },
    dispose() { rec.disposed = true },
    isIdle: () => (opts.idleWhen ? opts.idleWhen() : false),
    /** test helper: run one frame now */
    _frame(now) { if (!rec.disposed) { rec.draws++; draw(now) } },
  }
}

// ---- theming -----------------------------------------------------------------------------------------------
export const useTheme = () => ({ resolvedMode: 'dark', themeName: 'default', theme: { name: 'default' }, availableThemes: [],
  setTheme: unmodelled('useTheme().setTheme'), setMode: unmodelled('useTheme().setMode'), previewTheme: unmodelled('previewTheme') })
export const requestTheme = name => { calls.requestTheme.push(name); return false }
export const setAccentOverride = hex => { calls.accent.push(hex) }
export const $accentOverride = atom(null)
export const cn = (...xs) => xs.flat().filter(Boolean).join(' ')
export const haptic = () => {}

// ---- area constants (values copied from v0.22.7) -----------------------------------------------------------
export const PANES_AREA = 'panes'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const TITLEBAR_AREAS = { center: 'titleBar.center', left: 'titleBar.left', right: 'titleBar.right' }
export const SESSION_ROW_AREAS = { leading: 'sessionRow.leading', trailing: 'sessionRow.trailing' }
export const COMPOSER_AREAS = { top: 'composer.top', bottom: 'composer.bottom', underside: 'composer.underside',
  leading: 'composer.leading', actions: 'composer.actions', middleware: 'composer.middleware',
  attachments: 'composer.attachments', microActions: 'composer.microActions', atCompletions: 'composer.atCompletions',
  modelPill: 'composer.modelPill', contextMenu: 'composer.contextMenu' }
export const THEMES_AREA = 'themes'
export const PALETTE_AREA = 'palette'
export const KEYBINDS_AREA = 'keybinds'

// ---- stubs -------------------------------------------------------------------------------------------------
function unmodelled(name) {
  return () => { throw new Error(`fake SDK: ${name} is not modelled by the contract (see contract/README.md)`) }
}
function passthrough(name) {
  const C = props => jsx('x-' + name, { ...props })
  C.displayName = name
  return C
}
function constant(name) { return name }

export const APPEARANCE_AREAS = constant('APPEARANCE_AREAS')
export const APPROVAL_RESPOND_TIMEOUT_MS = constant('APPROVAL_RESPOND_TIMEOUT_MS')
export const BOT_CHAT_SESSION_HYDRATION_TIMEOUT_MS = constant('BOT_CHAT_SESSION_HYDRATION_TIMEOUT_MS')
export const Badge = passthrough('Badge')
export const Blobatar = passthrough('Blobatar')
export const Button = passthrough('Button')
export const CHAT_EMPTY_AREA = constant('CHAT_EMPTY_AREA')
export const CapabilitiesView = passthrough('CapabilitiesView')
export const Checkbox = passthrough('Checkbox')
export const Codicon = passthrough('Codicon')
export const ColorSwatches = passthrough('ColorSwatches')
export const ConfirmDialog = passthrough('ConfirmDialog')
export const ConnectionGlyph = passthrough('ConnectionGlyph')
export const ConnectorsTab = passthrough('ConnectorsTab')
export const ContextMenu = passthrough('ContextMenu')
export const ContextMenuCheckboxItem = passthrough('ContextMenuCheckboxItem')
export const ContextMenuContent = passthrough('ContextMenuContent')
export const ContextMenuItem = passthrough('ContextMenuItem')
export const ContextMenuSeparator = passthrough('ContextMenuSeparator')
export const ContextMenuSub = passthrough('ContextMenuSub')
export const ContextMenuSubContent = passthrough('ContextMenuSubContent')
export const ContextMenuSubTrigger = passthrough('ContextMenuSubTrigger')
export const ContextMenuTrigger = passthrough('ContextMenuTrigger')
export const Contribute = passthrough('Contribute')
export const CopyButton = passthrough('CopyButton')
export const DEFAULT_REASONING_EFFORT = constant('DEFAULT_REASONING_EFFORT')
export const DEFAULT_SESSION_HYDRATION_TIMEOUT_MS = constant('DEFAULT_SESSION_HYDRATION_TIMEOUT_MS')
export const DecodeText = passthrough('DecodeText')
export const Dialog = passthrough('Dialog')
export const DialogContent = passthrough('DialogContent')
export const DialogDescription = passthrough('DialogDescription')
export const DialogFooter = passthrough('DialogFooter')
export const DialogHeader = passthrough('DialogHeader')
export const DialogTitle = passthrough('DialogTitle')
export const DialogTrigger = passthrough('DialogTrigger')
export const DisclosureCaret = passthrough('DisclosureCaret')
export const DropdownMenu = passthrough('DropdownMenu')
export const DropdownMenuContent = passthrough('DropdownMenuContent')
export const DropdownMenuItem = passthrough('DropdownMenuItem')
export const DropdownMenuSeparator = passthrough('DropdownMenuSeparator')
export const DropdownMenuTrigger = passthrough('DropdownMenuTrigger')
export const EmptyState = passthrough('EmptyState')
export const ErrorState = passthrough('ErrorState')
export const FadeScroll = passthrough('FadeScroll')
export const GHOST_ICON_BTN = constant('GHOST_ICON_BTN')
export const GlyphSpinner = passthrough('GlyphSpinner')
export const HYDRATION_SYNC_BADGE_TIMEOUT_MS = constant('HYDRATION_SYNC_BADGE_TIMEOUT_MS')
export const Input = passthrough('Input')
export const KANBAN_CARD_AREAS = constant('KANBAN_CARD_AREAS')
export const KANBAN_CARD_BADGE_HUES = constant('KANBAN_CARD_BADGE_HUES')
export const KANBAN_CARD_BADGE_LIMITS = constant('KANBAN_CARD_BADGE_LIMITS')
export const KanbanCardBadges = passthrough('KanbanCardBadges')
export const Kbd = passthrough('Kbd')
export const KbdGroup = passthrough('KbdGroup')
export const ListRow = passthrough('ListRow')
export const Loader = passthrough('Loader')
export const LocalizedTabTitle = passthrough('LocalizedTabTitle')
export const LogView = passthrough('LogView')
export const LruCache = passthrough('LruCache')
export const MODEL_MENU_ROW_AREA = constant('MODEL_MENU_ROW_AREA')
export const MessageTextContent = passthrough('MessageTextContent')
export const ModelCatalogMenu = passthrough('ModelCatalogMenu')
export const ModelMenuCloseContext = passthrough('ModelMenuCloseContext')
export const PLUGIN_APP_ACTIONS = constant('PLUGIN_APP_ACTIONS')
export const PRIMARY_ICON_BTN = constant('PRIMARY_ICON_BTN')
export const PROFILE_SWATCHES = constant('PROFILE_SWATCHES')
export const PanelAction = passthrough('PanelAction')
export const PanelAddButton = passthrough('PanelAddButton')
export const PanelBlock = passthrough('PanelBlock')
export const PanelBody = passthrough('PanelBody')
export const PanelDetail = passthrough('PanelDetail')
export const PanelEmpty = passthrough('PanelEmpty')
export const PanelHeader = passthrough('PanelHeader')
export const PanelList = passthrough('PanelList')
export const PanelListRow = passthrough('PanelListRow')
export const PanelMeta = passthrough('PanelMeta')
export const PanelPill = passthrough('PanelPill')
export const PanelRowMenu = passthrough('PanelRowMenu')
export const PanelSectionLabel = passthrough('PanelSectionLabel')
export const Popover = passthrough('Popover')
export const PopoverContent = passthrough('PopoverContent')
export const PopoverTrigger = passthrough('PopoverTrigger')
export const REASONING_EFFORTS = constant('REASONING_EFFORTS')
export const REASONING_EFFORT_VALUES = constant('REASONING_EFFORT_VALUES')
export const ROUTES_AREA = constant('ROUTES_AREA')
export const RowButton = passthrough('RowButton')
export const SETTINGS_PLUGINS_AREA = constant('SETTINGS_PLUGINS_AREA')
export const SIDEBAR_NAV_AREA = constant('SIDEBAR_NAV_AREA')
export const SIDEBAR_NAV_PREFS_AREA = constant('SIDEBAR_NAV_PREFS_AREA')
export const SIDEBAR_PROFILE_GROUP_HEADER_AREA = constant('SIDEBAR_PROFILE_GROUP_HEADER_AREA')
export const SIDEBAR_ROW_LEAD = constant('SIDEBAR_ROW_LEAD')
export const SIDEBAR_TRUNCATED_LEADING = constant('SIDEBAR_TRUNCATED_LEADING')
export const SandboxedFrame = passthrough('SandboxedFrame')
export const ScrollArea = passthrough('ScrollArea')
export const SearchField = passthrough('SearchField')
export const SegmentedControl = passthrough('SegmentedControl')
export const Select = passthrough('Select')
export const SelectContent = passthrough('SelectContent')
export const SelectItem = passthrough('SelectItem')
export const SelectTrigger = passthrough('SelectTrigger')
export const SelectValue = passthrough('SelectValue')
export const Separator = passthrough('Separator')
export const SessionStatusDot = passthrough('SessionStatusDot')
export const SidebarRowLead = passthrough('SidebarRowLead')
export const Skeleton = passthrough('Skeleton')
export const StatusDot = passthrough('StatusDot')
export const Streamdown = passthrough('Streamdown')
export const Switch = passthrough('Switch')
export const TOOL_MEDIA_RENDERER_AREA = constant('TOOL_MEDIA_RENDERER_AREA')
export const TRANSCRIPT_DIRECTIVE_AREA = constant('TRANSCRIPT_DIRECTIVE_AREA')
export const Tabs = passthrough('Tabs')
export const TabsList = passthrough('TabsList')
export const TabsTrigger = passthrough('TabsTrigger')
export const Textarea = passthrough('Textarea')
export const Tip = passthrough('Tip')
export const ToggleRow = passthrough('ToggleRow')
export const ToolsetConfigPanel = passthrough('ToolsetConfigPanel')
export const Tooltip = passthrough('Tooltip')
export const TooltipContent = passthrough('TooltipContent')
export const TooltipProvider = passthrough('TooltipProvider')
export const TooltipTrigger = passthrough('TooltipTrigger')
export const WORKSPACE_PAGE_HEADER_AREA = constant('WORKSPACE_PAGE_HEADER_AREA')
export const Wordmark = passthrough('Wordmark')
export const WorkspacePageHeaderControl = passthrough('WorkspacePageHeaderControl')
export const ackStoredSessionId = unmodelled('ackStoredSessionId')
export const blobatarSvg = unmodelled('blobatarSvg')
export const captureGatewayFileDownload = unmodelled('captureGatewayFileDownload')
export const catalogProviderMatches = unmodelled('catalogProviderMatches')
export const coarseElapsed = unmodelled('coarseElapsed')
export const compactNumber = unmodelled('compactNumber')
export const composerInputBacking = unmodelled('composerInputBacking')
export const composerSurfaceRing = unmodelled('composerSurfaceRing')
export const contrastRatio = unmodelled('contrastRatio')
export const evaluateRuntimeReadiness = unmodelled('evaluateRuntimeReadiness')
export const fmtDateTime = unmodelled('fmtDateTime')
export const fmtDayTime = unmodelled('fmtDayTime')
export const forgetSessionUnread = unmodelled('forgetSessionUnread')
export const formatAgo = unmodelled('formatAgo')
export const formatModifierToken = unmodelled('formatModifierToken')
export const gatewayActivationEpoch = unmodelled('gatewayActivationEpoch')
export const hexToOklch = unmodelled('hexToOklch')
export const hueDelta = unmodelled('hueDelta')
export const isSubmitEnter = unmodelled('isSubmitEnter')
export const markSessionUnreadFinished = unmodelled('markSessionUnreadFinished')
export const maxChroma = unmodelled('maxChroma')
export const mixOklab = unmodelled('mixOklab')
export const nextRunOverdueMs = unmodelled('nextRunOverdueMs')
export const normalizeHex = unmodelled('normalizeHex')
export const oklchToHex = unmodelled('oklchToHex')
export const oklchToSrgb255 = unmodelled('oklchToSrgb255')
export const pluginSettingsHref = unmodelled('pluginSettingsHref')
export const profileColor = unmodelled('profileColor')
export const profileColorSoft = unmodelled('profileColorSoft')
export const queryClient = unmodelled('queryClient')
export const randomUuid = unmodelled('randomUuid')
export const readableOn = unmodelled('readableOn')
export const reasoningEffortLabel = unmodelled('reasoningEffortLabel')
export const relativeTime = unmodelled('relativeTime')
export const resolveSiblingWsUrl = unmodelled('resolveSiblingWsUrl')
export const retintTheme = unmodelled('retintTheme')
export const surfaceModelSwitchConfirm = unmodelled('surfaceModelSwitchConfirm')
export const themeHue = unmodelled('themeHue')
export const translateNow = unmodelled('translateNow')
export const useGatewayActivationEpoch = unmodelled('useGatewayActivationEpoch')
export const useGrabScroll = unmodelled('useGrabScroll')
export const useI18n = unmodelled('useI18n')
export const useMutation = unmodelled('useMutation')
export const usePluginI18n = unmodelled('usePluginI18n')
export const useQuery = unmodelled('useQuery')
export const useQueryClient = unmodelled('useQueryClient')
export const writeClipboardText = unmodelled('writeClipboardText')
