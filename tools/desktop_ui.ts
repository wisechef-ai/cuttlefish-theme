/** UI drivers for the real desktop build: go through the same controls a user clicks. */
import type { Page } from '@playwright/test'

/** Navigate the HashRouter without touching app state. */
export async function gotoRoute(page: Page, route: string): Promise<void> {
  await page.evaluate(r => {
    window.location.hash = `#${r}`
  }, route)
  await page.waitForTimeout(800)
}

export interface SwitchInfo {
  label: string
  checked: boolean
  disabled: boolean
}

export async function listSwitches(page: Page): Promise<SwitchInfo[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('[role="switch"]')].map(el => ({
      label: el.getAttribute('aria-label') ?? '',
      checked: el.getAttribute('aria-checked') === 'true' || el.getAttribute('data-state') === 'checked',
      disabled: el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true',
    })),
  )
}

/**
 * Capabilities ▸ Plugins → search → open the package card → flip the DESKTOP half
 * switch in the detail (`Desktop: <name>`, plugins-tab.tsx PackageRow). That is
 * the second consent (plan §1.5 step 3) and touches ONLY the app-level half —
 * the card-level switch would also enable the agent half (plugins.enabled).
 * Returns the switch's checked state afterwards.
 */
export async function enablePluginViaSettings(page: Page, name: string, timeoutMs = 30_000): Promise<boolean> {
  // `name` is the DISPLAY name (the desktop plugin's `name`, e.g. "CF Spike"); the
  // installed card's entry id is `installed:<folder id>` and the text search does
  // not match the folder id — observed on 7bf352567f0.
  await gotoRoute(page, '/capabilities?tab=plugins')
  await page.getByText('Installed', { exact: true }).first().click({ timeout: timeoutMs })
  await page.waitForTimeout(800)

  const card = page.locator(`[data-catalog-card] [aria-haspopup="dialog"][aria-label="${name}"]`).first()

  await card.waitFor({ state: 'visible', timeout: timeoutMs })
  await card.click()

  const label = `Desktop: ${name}`
  const sw = page.locator(`[role="switch"][aria-label="${label}"]`).first()

  await sw.waitFor({ state: 'visible', timeout: timeoutMs })

  const isOn = async () =>
    (await sw.getAttribute('aria-checked')) === 'true' || (await sw.getAttribute('data-state')) === 'checked'

  if (!(await isOn())) {
    await sw.click()
  }

  await page.waitForFunction(
    l => {
      const el = document.querySelector(`[role="switch"][aria-label="${l}"]`)

      return el?.getAttribute('aria-checked') === 'true' || el?.getAttribute('data-state') === 'checked'
    },
    label,
    { timeout: timeoutMs },
  )

  return isOn()
}
