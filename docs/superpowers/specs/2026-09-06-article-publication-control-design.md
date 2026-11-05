# Article Publication Control Design

## Goal

Move article visibility controls into the editor header, make publication and
draft-update state immediately legible, and remove the oversized bottom action
area.

## Editor Header

The right side of the article editor header contains a compact publication
control group. It includes a labelled `公开` switch and a live status message.
It shares the header action area with the editor title instead of appearing
below the Markdown editor.

## Publication Semantics

- For an unpublished article, switching `公开` on publishes its current draft.
- For a published article with no draft, switching `公开` off unpublishes it.
- For a published article with an unpublished draft, the switch remains on:
  it represents the visibility of the existing public version. The group
  shows `有未发布修改` and provides a compact `发布更新` command that explicitly
  replaces the public version with the draft.

The existing publication, unpublication, and publish-update endpoints retain
their server-side behavior; this change only relocates and clarifies their
controls.

## Save Status

The same header group surfaces the current editor-save state: `保存中`,
`草稿已保存`, `保存失败`, `已公开`, or `有未发布修改`. A failed save never changes
the publication toggle and is not reported as saved. Subsequent editor input
continues through the existing autosave retry path.

## Removed Controls

The full-width normal form submit button and the detached bottom `Unpublish`
button area are removed. The editor remains usable without JavaScript through
the header forms and buttons.

## Verification

Template and route tests cover the header switch/action states, the
published-with-draft reminder and explicit update action, and absence of the
old bottom action area. Browser tests cover synchronization of autosave status
into the header status element and preserve failure-state behavior.
