import type { Resource, Terrain } from "../protocol/types";

export const SEA = 0x1f5f8b;
export const SEA_EDGE = 0x2a6e9b;
export const WAVE = 0xbfe3f2;
export const SHALLOWS = 0x3f97b5;
export const SAND = 0xead6a0;
export const SAND_EDGE = 0xc9ad6e;
export const FISHING = 0x2f7aa6;
export const OUTLINE = 0x1d2a2e;
export const TOKEN_BG = 0xfbf3dc;
export const TOKEN_RING = 0xc9a86a;
export const TOKEN_TEXT = 0x1d2a2e;
export const TOKEN_RED = 0xb3261e;
export const SHADOW = 0x08202e;
export const PIER = 0x8a5a33;
export const PIER_DARK = 0x4e301a;
export const PIER_LIGHT = 0xa8733f;
export const ROPE = 0xd8b77a;
export const RIBBON_DARK = 0xb08a4a;
export const HIGHLIGHT = 0xffe066;

export const TERRAIN: Record<Terrain, number> = {
  forest: 0x3f8f45,
  pasture: 0xa5d16a,
  fields: 0xf0c94f,
  hills: 0xcd6f45,
  mountains: 0x9a9da3,
  desert: 0xecd9a6,
};

/** A darker shade of the terrain for each hex's rim. */
export const TERRAIN_EDGE: Record<Terrain, number> = {
  forest: 0x235b28,
  pasture: 0x6f9a3c,
  fields: 0xb68d1f,
  hills: 0x8f4425,
  mountains: 0x63666c,
  desert: 0xb89e62,
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
