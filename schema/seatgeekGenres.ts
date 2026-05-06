import { sql } from "drizzle-orm";
import { varchar, boolean, timestamp, pgTable } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getSeatgeekGenres } from "@/lib/api/seatgeekGenres/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const seatgeekGenres = pgTable("seatgeek_genres", {
  id: varchar("id", { length: 191 })
    .primaryKey()
    .$defaultFn(() => nanoid()),
  seatgeekId: varchar("seatgeek_id", { length: 256 }).notNull().unique(),
  name: varchar("name", { length: 256 }).notNull(),
  slug: varchar("slug", { length: 256 }).notNull(),
  image: varchar("image", { length: 256 }),
  primary: boolean("primary").notNull(),

  createdAt: timestamp("created_at")
    .notNull()
    .default(sql`now()`),
  updatedAt: timestamp("updated_at")
    .notNull()
    .default(sql`now()`),
});

// Schema for seatgeekGenres - used to validate API requests
const baseSchema = createSelectSchema(seatgeekGenres).omit(timestamps);

export const insertSeatgeekGenreSchema = createInsertSchema(seatgeekGenres).omit(timestamps);
export const insertSeatgeekGenreParams = baseSchema
  .extend({
    primary: z.coerce.boolean(),
  })
  .omit({
    id: true,
  });

export const updateSeatgeekGenreSchema = baseSchema;
export const updateSeatgeekGenreParams = baseSchema.extend({
  primary: z.coerce.boolean(),
});
export const seatgeekGenreIdSchema = baseSchema.pick({ id: true });

// Types for seatgeekGenres - used to type API request params and within Components
export type SeatgeekGenre = typeof seatgeekGenres.$inferSelect;
export type NewSeatgeekGenre = z.infer<typeof insertSeatgeekGenreSchema>;
export type NewSeatgeekGenreParams = z.infer<typeof insertSeatgeekGenreParams>;
export type UpdateSeatgeekGenreParams = z.infer<typeof updateSeatgeekGenreParams>;
export type SeatgeekGenreId = z.infer<typeof seatgeekGenreIdSchema>["id"];

// this type infers the return from getSeatgeekGenres() - meaning it will include any joins
export type CompleteSeatgeekGenre = Awaited<ReturnType<typeof getSeatgeekGenres>>["seatgeekGenres"][number];
