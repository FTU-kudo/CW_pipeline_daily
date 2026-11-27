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

test('Bento KPI tiers fill the overview width and retain contrast-aware scales', () => {
  assert.match(css, /#ov-grid\s*\{\s*display:\s*flex;\s*flex-direction:\s*column;[\s\S]*?width:\s*100%/);
  assert.match(css, /#ov-grid > \.ov-tier\s*\{\s*width:\s*100%;/);
  assert.match(css, /\.ov-tier-primary\s*\{\s*grid-template-columns:\s*repeat\(3,/);
  assert.match(css, /\.ov-tier-secondary\s*\{\s*grid-template-columns:\s*repeat\(6,/);
  assert.match(css, /\.ov-icon-badge\s*\{[\s\S]*?flex:\s*0 0 36px;[\s\S]*?width:\s*36px;[\s\S]*?height:\s*36px/);
  assert.match(css, /\.ov-icon-badge \.ov-ico\s*\{[\s\S]*?width:\s*18px;[\s\S]*?height:\s*18px/);
  assert.match(css, /\.ov-k-title\s*\{[\s\S]*?color:\s*var\(--text\);[\s\S]*?font-size:\s*14px;[\s\S]*?font-weight:\s*680;[\s\S]*?white-space:\s*nowrap/);
  assert.match(css, /\.ov-k > \.ov-badge\s*\{[\s\S]*?white-space:\s*nowrap;[\s\S]*?text-overflow:\s*clip/);
  assert.match(css, /\.ov-card-primary > \.ov-v\s*\{[\s\S]*?font-size:\s*clamp\(32px/);
  assert.match(css, /\.ov-card-secondary > \.ov-v\s*\{[\s\S]*?font-size:\s*clamp\(24px/);
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
