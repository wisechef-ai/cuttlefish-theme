# Cuttlefish — reading the language

You open a terminal, type `hermes`, and the window has a skin. This document
explains how to read it.

The theme is **a language, not decoration**. It has exactly two channels, and
they answer two different questions:

| channel | surface | question it answers | varies by |
|---|---|---|---|
| **Identity** | the transcript background | *Which window is this?* | session |
| **State** | the status bar | *Does this window want me?* | what the agent is doing |

Everything below follows from one rule: **the two channels never share a
surface.** If you remember nothing else, remember that.

---

## 1. The background is your window's face

Every session gets its own field of colour — a dark ground carrying sparse
brighter pigment, like the skin of a cuttlefish at rest. It is derived from the
session id, so:

- **It is stable.** The same session always looks the same. Close the laptop,
  reconnect over SSH, come back tomorrow — same face.
- **It is unique.** Two windows side by side do not look alike.
- **It never changes while you work.** Not when the agent is thinking, not when
  a tool runs, not when something fails.

That last point is the important one, and it was a deliberate decision:

> *"per session no big background changes — the background change makes the
> recognition of terminal harder"* — Adam, 2026-09-12

If the background changed when a window needed attention, you would lose the
window exactly when you were looking for it. So the face stays still. **Use it
to find a window, never to learn what a window is doing.**

**How to use it in practice:** with ten or twenty terminals open across screens,
you learn your windows by their colour the way you learn a book by its spine.
"The violet one is the deploy," "the teal one is the long build." That
recognition is the whole point.

---

## 2. Under text, the skin contracts

Look closely and you will notice the background is **calmer where text sits**
and **louder in the empty space** to the right of your lines and below them.

That is not two different backgrounds. It is one mechanism, borrowed from the
animal.

A real cuttlefish chromatophore is a muscular sac of pigment. To go pale, it
**contracts** — the sac shrinks and the pale *leucophore* layer beneath shows
through. It does not paint itself another colour; it reveals what was already
underneath.

The theme does the same thing. Where a glyph sits, the pigment contracts:

- the **hue stays the same** (measured: the colour shifts by well under a
  degree — it is the same colour, not a substitute)
- the **lightness variation is compressed**, so your eye is not fighting a
  bright cell next to a dark one while reading
- the **texture survives** — it goes quiet, not blank

So text is readable, and the skin is still visibly there. If the field under
your text were flat black, that would be a bug, not the design — a flat
background is just an unthemed terminal.

**How to use it in practice:** nothing to do. This is the part that gets out of
your way. But it explains why the window looks livelier as you scroll into
empty space — that is the skin uncontracted.

---

## 3. The status bar is the only thing that speaks

All state lives on the bar at the bottom. Unlike the background, **the bar reads
the same in every window**, because an alarm that looked different in each
terminal would not be an alarm at all.

Three states:

| bar | name | what it means | what to do |
|---|---|---|---|
| **calm, in your session's hue** | `resting` | working, or idle. Nothing needed. | nothing |
| **amber** | `attention` | the agent is waiting on *you* — a question, a confirmation, an approval | go to that window |
| **red** | `fault` | something failed and stopped | go read the error |

Amber and red are deliberately far apart on the colour wheel (more than 25° of
hue separation, verified by test) so you can tell them apart at a glance across
a room, not just side by side.

The bar **always paints**. If you ever see a bar in stock Hermes gold, the theme
has fallen back and something is wrong with the install.

**How to use it in practice:** scan the bars, not the backgrounds. Amber means
*you* are the bottleneck. Red means it already stopped. Anything else means
leave it alone.

---

## 4. The two-glance workflow

Put the channels together and there is a rhythm to using this:

1. **Glance one — scan for colour on the bars.** Amber anywhere? Red anywhere?
   This is a peripheral-vision job; you do not need to read anything.
2. **Glance two — use the backgrounds to navigate.** You know which window is
   which by its face, so you go straight to the right one instead of
   alt-tabbing through six terminals reading titles.

The reason the split exists: the surface that helps you *find* a window (a big,
stable, per-session field) and the surface that tells you a window *needs* you
(a small, loud, universal signal) have opposite requirements. Identity must be
unique and still; state must be identical everywhere and must move. Put them on
one surface and each one ruins the other.

---

## 5. What is deliberately absent

- **No notification, no bell, no popup.** The bar changing colour is the entire
  signal. It is ambient — you notice it when you look, and it never interrupts.
- **No meaning in the pattern itself.** The mottle, the waves, the pearl
  scatter: these carry identity, not information. There is no "busy pattern" to
  decode. If you find yourself reading the texture, you are over-reading it.
- **No title-bar changes.** Window and tab titles are left alone on purpose.

---

## 6. Quick reference

```
BACKGROUND  = who         stable, unique per session, never moves
  under text              calmer, same hue, still textured (contraction)
  in open space           louder, the skin at rest

STATUS BAR  = what        identical in every session for a given state
  session hue             resting      — nothing needed
  amber                   attention    — the agent is waiting on YOU
  red                     fault        — something failed, go look
```

One sentence: **the background tells you which window this is; the bar tells you
whether it wants you.**
