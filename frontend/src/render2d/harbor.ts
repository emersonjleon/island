// Harbours: two plank jetties from the shore to a round rope-ringed medallion out at
// sea. The medallion shows the resource (colour + icon, or an anchor for any
// resource) and a parchment ribbon with the trade ratio.
import { Container, Graphics, Text } from "pixi.js";

import type { Pt } from "../board/geometry";
import type { Resource } from "../protocol/types";
import * as P from "./palette";

/** 24×24 icons, white, matching the HUD's resource icons. */
const ICON: Record<Resource | "any", string> = {
  lumber: '<path d="M12 2 5 12h4l-3 5h12l-3-5h4z" fill="#fff"/><rect x="10.5" y="17" width="3" height="5" rx="1" fill="#fff"/>',
  brick: '<rect x="2" y="13" width="9" height="5" rx="1" fill="#fff"/><rect x="13" y="13" width="9" height="5" rx="1" fill="#fff"/>'
    + '<rect x="7.5" y="7" width="9" height="5" rx="1" fill="#fff"/>',
  wool: '<path d="M8 9a3 3 0 0 1 5-1.5A3 3 0 0 1 18 10a3 3 0 0 1-1 5.5H8A3 3 0 0 1 8 9z" fill="#fff"/>'
    + '<ellipse cx="5" cy="11" rx="2.6" ry="2.1" fill="#fff"/><rect x="8.2" y="15" width="1.8" height="4" fill="#fff"/>'
    + '<rect x="14.2" y="15" width="1.8" height="4" fill="#fff"/>',
  grain: '<rect x="11.1" y="8" width="1.8" height="14" rx="0.9" fill="#fff"/><ellipse cx="12" cy="4" rx="1.8" ry="2.8" fill="#fff"/>'
    + '<ellipse cx="9" cy="8" rx="1.8" ry="3" fill="#fff"/><ellipse cx="15" cy="8" rx="1.8" ry="3" fill="#fff"/>'
    + '<ellipse cx="9" cy="13" rx="1.8" ry="3" fill="#fff"/><ellipse cx="15" cy="13" rx="1.8" ry="3" fill="#fff"/>',
  ore: '<path d="M3 19 8 9l4 3 3-6 6 13z" fill="#fff"/>',
  fish: '<path d="M3 12c3-5 9-6 13-3l5-3v12l-5-3c-4 3-10 2-13-3z" fill="#fff"/>',
  any: '<circle cx="12" cy="5" r="2.4" fill="none" stroke="#fff" stroke-width="2"/><rect x="11" y="7" width="2" height="13" fill="#fff"/>'
    + '<rect x="7" y="9.5" width="10" height="2" rx="1" fill="#fff"/>'
    + '<path d="M4 13c0 5 4 8 8 8s8-3 8-8l-2.2 1.6C17 18 15 19 12 19s-5-1-5.8-4.4z" fill="#fff"/>',
};

const ICON_DARK: Partial<Record<Resource | "any", number>> = { wool: 0x2f4a1a, grain: 0x5a4208, ore: 0x2c3036 };
const ANY_COLOUR = 0x2a6f9a;

function icon(kind: Resource | "any", size: number, tint: number): Graphics {
  const g = new Graphics().svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">${ICON[kind]}</svg>`);
  g.scale.set(size / 24);
  g.pivot.set(12, 12);
  g.tint = tint;
  return g;
}

/** One harbour. ``a`` and ``b`` are the shore vertices and ``pos`` the medallion
 * centre, all in pixels; ``u`` is the hex radius in pixels. */
export function drawHarbor(a: Pt, b: Pt, pos: Pt, ratio: number, resource: Resource | null, u: number): Container {
  const box = new Container();
  const piers = new Graphics();
  for (const end of [a, b]) jetty(piers, { x: end.x + (pos.x - end.x) * 0.15, y: end.y + (pos.y - end.y) * 0.15 }, pos, u);
  box.addChild(piers);

  const r = u * 0.27;
  const colour = resource ? P.RESOURCE[resource] : ANY_COLOUR;
  const medal = new Graphics()
    .circle(pos.x + 2, pos.y + 3, r * 1.08).fill({ color: P.SHADOW, alpha: 0.4 })
    // rope ring
    .circle(pos.x, pos.y, r).fill(P.ROPE).stroke({ width: 1.5, color: P.PIER_DARK })
    .circle(pos.x, pos.y, r * 0.8).fill(colour).stroke({ width: 1.5, color: P.PIER_DARK, alpha: 0.6 })
    // a soft highlight on the top-left of the medallion
    .ellipse(pos.x - r * 0.25, pos.y - r * 0.38, r * 0.4, r * 0.18).fill({ color: 0xffffff, alpha: 0.25 });
  for (let i = 0; i < 12; i++) {
    const t = (Math.PI * 2 * i) / 12;
    medal.moveTo(pos.x + Math.cos(t) * r * 0.82, pos.y + Math.sin(t) * r * 0.82)
      .lineTo(pos.x + Math.cos(t + 0.3) * r * 0.98, pos.y + Math.sin(t + 0.3) * r * 0.98);
  }
  medal.stroke({ width: 1, color: P.PIER_DARK, alpha: 0.55 });
  box.addChild(medal);

  const kind = resource ?? "any";
  const ic = icon(kind, r * 1.0, ICON_DARK[kind] ?? 0xffffff);
  ic.position.set(pos.x, pos.y - r * 0.12);
  box.addChild(ic);

  // Parchment ribbon with the ratio, across the bottom of the medallion.
  const rw = r * 1.55;
  const rh = r * 0.62;
  const ry = pos.y + r * 0.62;
  const ribbon = new Graphics()
    .poly([pos.x - rw / 2 - rh * 0.35, ry - rh / 2 + 1, pos.x - rw / 2, ry, pos.x - rw / 2 - rh * 0.35, ry + rh / 2 + 1,
           pos.x - rw / 2 + 2, ry + rh / 2 + 1]).fill(P.RIBBON_DARK)
    .poly([pos.x + rw / 2 + rh * 0.35, ry - rh / 2 + 1, pos.x + rw / 2, ry, pos.x + rw / 2 + rh * 0.35, ry + rh / 2 + 1,
           pos.x + rw / 2 - 2, ry + rh / 2 + 1]).fill(P.RIBBON_DARK)
    .roundRect(pos.x - rw / 2, ry - rh / 2, rw, rh, rh * 0.25).fill(P.TOKEN_BG).stroke({ width: 1.2, color: P.PIER_DARK });
  const label = new Text({ text: `${ratio}:1`, style: { fontFamily: "Georgia, 'Times New Roman', serif", fontSize: rh * 0.82,
    fontWeight: "700", fill: P.TOKEN_TEXT } });
  label.anchor.set(0.5, 0.52);
  label.position.set(pos.x, ry);
  box.addChild(ribbon, label);
  return box;
}

/** A plank jetty from ``s`` to ``e``: posts, a dark frame and lighter planks across it. */
function jetty(g: Graphics, s: Pt, e: Pt, u: number): void {
  const dx = e.x - s.x;
  const dy = e.y - s.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const w = u * 0.055;
  const quad = (k0: number, k1: number, half: number) => [
    s.x + dx * k0 + nx * half, s.y + dy * k0 + ny * half, s.x + dx * k1 + nx * half, s.y + dy * k1 + ny * half,
    s.x + dx * k1 - nx * half, s.y + dy * k1 - ny * half, s.x + dx * k0 - nx * half, s.y + dy * k0 - ny * half,
  ];
  g.poly(quad(0, 1, w * 1.25)).fill({ color: P.SHADOW, alpha: 0.25 });
  g.poly(quad(0, 1, w)).fill(P.PIER_DARK);
  const planks = Math.max(3, Math.round(len / (u * 0.06)));
  for (let i = 0; i < planks; i++) {
    const k0 = i / planks + 0.012;
    const k1 = (i + 1) / planks - 0.012;
    g.poly(quad(k0, k1, w * 0.78)).fill(i % 2 ? P.PIER : P.PIER_LIGHT);
  }
  // posts at the shore end
  for (const side of [1, -1]) g.circle(s.x + nx * w * side, s.y + ny * w * side, w * 0.45).fill(P.PIER_DARK);
}
