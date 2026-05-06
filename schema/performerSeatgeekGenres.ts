import { sql } from "drizzle-orm";
import { varchar, timestamp, pgTable, unique } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";
import { performers } from "./performers";
import { seatgeekGenres } from "./seatgeekGenres";
import { type getPerformerSeatgeekGenres } from "@/lib/api/performerSeatgeekGenres/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const performerSeatgeekGenres = pgTable(
  "performer_seatgeek_genres",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    performerId: varchar("performer_id", { length: 256 })
      .references(() => performers.id, { onDelete: "cascade" })
      .notNull(),
    seatgeekGenreId: varchar("seatgeek_genre_id", { length: 256 })
      .references(() => seatgeekGenres.id, { onDelete: "cascade" })
      .notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    unq: unique().on(t.performerId, t.seatgeekGenreId),
  })
);

// Schema for performerSeatgeekGenres - used to validate API requests
const baseSchema = createSelectSchema(performerSeatgeekGenres).omit(timestamps);

export const insertPerformerSeatgeekGenreSchema = createInsertSchema(performerSeatgeekGenres).omit(timestamps);
export const insertPerformerSeatgeekGenreParams = baseSchema
  .extend({
    performerId: z.coerce.string().min(1),
    seatgeekGenreId: z.coerce.string().min(1),
  })
  .omit({
    id: true,
  });

export const updatePerformerSeatgeekGenreSchema = baseSchema;
export const updatePerformerSeatgeekGenreParams = baseSchema.extend({
  performerId: z.coerce.string().min(1),
  seatgeekGenreId: z.coerce.string().min(1),
});
export const performerSeatgeekGenreIdSchema = baseSchema.pick({ id: true });

// Types for performerSeatgeekGenres - used to type API request params and within Components
export type PerformerSeatgeekGenre = typeof performerSeatgeekGenres.$inferSelect;
export type NewPerformerSeatgeekGenre = z.infer<typeof insertPerformerSeatgeekGenreSchema>;
export type NewPerformerSeatgeekGenreParams = z.infer<typeof insertPerformerSeatgeekGenreParams>;
export type UpdatePerformerSeatgeekGenreParams = z.infer<typeof updatePerformerSeatgeekGenreParams>;
export type PerformerSeatgeekGenreId = z.infer<typeof performerSeatgeekGenreIdSchema>["id"];

// this type infers the return from getPerformerSeatgeekGenres() - meaning it will include any joins
export type CompletePerformerSeatgeekGenre = Awaited<
  ReturnType<typeof getPerformerSeatgeekGenres>
>["performerSeatgeekGenres"][number];
