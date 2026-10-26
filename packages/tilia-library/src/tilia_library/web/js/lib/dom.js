// Typed DOM access, shared by all three pages.
//
// The lib types are deliberately conservative: querySelector is declared to
// return Element, querySelectorAll a NodeListOf<Element>, and an event's target
// an EventTarget. None of those carry .value, .dataset, .style or .closest, so
// correct code reads as a type error at every call site. Every selector in these
// pages targets an HTML element and every listener is attached to a DOM node, so
// narrowing once here beats a cast at each use.
//
// This is the one module deliberately shared across pages. It holds new code
// only — the functions that were copied between pages before have drifted apart
// and must not be merged without deciding each pair on its merits.

/**
 * @param {ParentNode} root
 * @param {string} sel
 * @returns {HTMLElement}
 */
export const q = (root, sel) => /** @type {HTMLElement} */ (root.querySelector(sel));

/**
 * @param {ParentNode} root
 * @param {string} sel
 * @returns {NodeListOf<HTMLElement>}
 */
export const qa = (root, sel) => /** @type {NodeListOf<HTMLElement>} */ (root.querySelectorAll(sel));

/**
 * The element an event fired on.
 * @param {Event} e
 * @returns {HTMLElement}
 */
export const evTarget = e => /** @type {HTMLElement} */ (e.target);

/**
 * Element.closest, narrowed. Declared to return Element, which carries neither
 * .dataset nor .style, and closest() is how these pages find the row or button
 * an event came from.
 * @param {Element} el
 * @param {string} sel
 * @returns {HTMLElement}
 */
export const closest = (el, sel) => /** @type {HTMLElement} */ (el.closest(sel));

/**
 * querySelector for a form control, where .value and .checked are the point.
 * @param {ParentNode} root
 * @param {string} sel
 * @returns {HTMLInputElement}
 */
export const qInput = (root, sel) => /** @type {HTMLInputElement} */ (root.querySelector(sel));

/**
 * @param {ParentNode} root
 * @param {string} sel
 * @returns {HTMLTextAreaElement}
 */
export const qArea = (root, sel) => /** @type {HTMLTextAreaElement} */ (root.querySelector(sel));

/**
 * @param {ParentNode} root
 * @param {string} sel
 * @returns {NodeListOf<HTMLInputElement>}
 */
export const qaInput = (root, sel) => /** @type {NodeListOf<HTMLInputElement>} */ (root.querySelectorAll(sel));
