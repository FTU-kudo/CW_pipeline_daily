import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../../docs/assets/ui.css', import.meta.url), 'utf8');
const html = readFileSync(new URL('../../docs/index.html', import.meta.url), 'utf8');

test('active app styles do not declare text below 12px', () => {
  for (const [file, content] of [['ui.css', css], ['index.html', html]]) {
    const sizes = [...content.matchAll(/font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px/g)]
      .map(match => Number(match[1]));
    assert.ok(sizes.every(size => size >= 12), `${file} contains a font-size declaration below 12px`);
    assert.doesNotMatch(content, /font-size\s*:\s*0(?:\s*[;}])/i, `${file} contains hidden zero-size text`);
    const shorthandSizes = [...content.matchAll(/font\s*:\s*(?:(?:normal|bold|[1-9]00)\s+)*([0-9]+(?:\.[0-9]+)?)px/g)]
      .map(match => Number(match[1]));
    assert.ok(shorthandSizes.every(size => size >= 12), `${file} contains a font shorthand below 12px`);
  }
});

test('KPI grid and contrast-aware scales match the redesign', () => {
  assert.match(css, /\.overview \.ov-grid\s*\{\s*grid-template-columns:\s*repeat\(4,/);
  assert.match(css, /\.overview \.ov-v[\s\S]*?font-size:\s*clamp\(24px, 1\.8vw, 26px\)/);
  assert.match(css, /--muted:\s*#475569/);
  assert.match(css, /--text:\s*#f8fafc/);
  assert.match(css, /--th-text:\s*#334155/);
});

test('main views use a segmented control and optional filters use pills', () => {
  assert.match(html, /class="nav-group view-group" role="tablist"/);
  assert.match(html, /class="nav-group nav-options" role="group"/);
  assert.match(css, /\.nav-group\[role="tablist"\] \.tab\.active\s*\{[\s\S]*?box-shadow:/);
  assert.match(css, /\.nav-options \.tab\.chip\s*\{[\s\S]*?border-radius:\s*999px/);
});

test('table, subtitle, callout, and weight hierarchy are explicit', () => {
  assert.match(css, /thead th\s*\{[\s\S]*?font-size:\s*12\.5px/);
  assert.match(css, /\.caption,[\s\S]*?max-width:\s*50rem/);
  assert.match(css, /\.valuation-provisional\s*\{[\s\S]*?font-size:\s*13px/);
  assert.match(css, /\.wbadge\s*\{[\s\S]*?font-size:\s*13px/);
});
