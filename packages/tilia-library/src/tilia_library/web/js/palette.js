// The colours the charts share.
export const TABLEAU = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
  '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];
export const FAMILY_COLORS = {
  verse: '#4e79a7', chorus: '#e15759', bridge: '#f28e2b', refrain: '#edc948',
  intro: '#bab0ac', outro: '#9c9c9c', prechorus: '#76b7b2', solo: '#59a14f',
  blues: '#b07aa1', instrumental: '#9c755f'
};
export const color = (fam, i = 0) => FAMILY_COLORS[fam] || TABLEAU[i % TABLEAU.length];
export const alpha = (hex, a) => hex + Math.round(a * 255).toString(16).padStart(2, '0');
