import { pgEnum } from "drizzle-orm/pg-core";

export const genreValues = [
  "americana",
  "bluegrass",
  "blues",
  "blues-rock",
  "classic-rock",
  "christian",
  "classical",
  "country-music",
  "edm",
  "folk",
  "funk",
  "hip-hop-rap",
  "indie",
  "indie-rock",
  "jamband",
  "jazz",
  "kpop",
  "latin",
  "livetronica",
  "metal",
  "pop",
  "prog-rock",
  "punk",
  "rhythm-and-blues-soul",
  "reggae",
  "rock",
] as const;

export const genreEnum = pgEnum("genre", genreValues);

export type Genre = (typeof genreValues)[number];
