import { sql } from "drizzle-orm";
import { varchar, timestamp, pgTable, unique, index } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";
import { performers } from "./performers";
import { type getPerformerGenres } from "@/lib/api/performerGenres/queries";
import { genreEnum } from "./genres";

import { nanoid, timestamps } from "@/lib/utils";

export const performerGenres = pgTable(
  "performer_genres",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    performerId: varchar("performer_id", { length: 256 })
      .references(() => performers.id, { onDelete: "cascade" })
      .notNull(),
    genre: genreEnum("genre").notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    unq: unique().on(t.performerId, t.genre),
    performerId: index().on(t.performerId),
    genre: index().on(t.genre),
  })
);

// Schema for performerGenres - used to validate API requests
const baseSchema = createSelectSchema(performerGenres).omit(timestamps);

export const insertPerformerGenreSchema = createInsertSchema(performerGenres).omit(timestamps);
export const insertPerformerGenreParams = baseSchema
  .extend({
    performerId: z.coerce.string().min(1),
  })
  .omit({
    id: true,
  });

export const updatePerformerGenreSchema = baseSchema;
export const updatePerformerGenreParams = baseSchema.extend({
  performerId: z.coerce.string().min(1),
});
export const performerGenreIdSchema = baseSchema.pick({ id: true });

// Types for performerGenres - used to type API request params and within Components
export type PerformerGenre = typeof performerGenres.$inferSelect;
export type NewPerformerGenre = z.infer<typeof insertPerformerGenreSchema>;
export type NewPerformerGenreParams = z.infer<typeof insertPerformerGenreParams>;
export type UpdatePerformerGenreParams = z.infer<typeof updatePerformerGenreParams>;
export type PerformerGenreId = z.infer<typeof performerGenreIdSchema>["id"];

// this type infers the return from getPerformerGenres() - meaning it will include any joins
export type CompletePerformerGenre = Awaited<ReturnType<typeof getPerformerGenres>>["performerGenres"][number];
