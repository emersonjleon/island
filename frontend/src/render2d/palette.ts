import type { Resource, Terrain } from "../protocol/types";

export const SEA = 0x2f6f9f;
export const SEA_EDGE = 0x285f88;
export const FISHING = 0x3f86b8;
export const OUTLINE = 0x1d2a2e;
export const TOKEN_BG = 0xf4ecd6;
export const TOKEN_TEXT = 0x1d2a2e;
export const TOKEN_RED = 0xb3261e;
export const HIGHLIGHT = 0xffe066;

export const TERRAIN: Record<Terrain, number> = {
  forest: 0x2e7d32,
  pasture: 0x9ccc65,
  fields: 0xf2c94c,
  hills: 0xc0603a,
  mountains: 0x8d8f94,
  desert: 0xe6d3a3,
};

export const RESOURCE: Record<Resource, number> = {
  lumber: 0x2e7d32, brick: 0xc0603a, wool: 0x9ccc65, grain: 0xf2c94c, ore: 0x8d8f94, fish: 0x3f86b8,
};

export const PLAYER: Record<string, number> = {
  red: 0xc8372d, blue: 0x2f5fb3, white: 0xf4f1e8, orange: 0xe58a1f, green: 0x3c8a3f, brown: 0x7a5232,
};

export function playerColour(name: string): number {
  return PLAYER[name] ?? 0x888888;
}

/** Number of pips under a dice number (probability out of 36). */
export function pips(token: number): number {
  return 6 - Math.abs(7 - token);
}
