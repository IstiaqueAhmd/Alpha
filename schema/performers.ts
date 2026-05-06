import { sql } from "drizzle-orm";
import { varchar, timestamp, pgTable, unique, integer } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getPerformers } from "@/lib/api/performers/queries";

import { nanoid, timestamps } from "@/lib/utils";
import { Event } from "./events";
import { genreEnum } from "./genres";

export const performers = pgTable(
  "performers",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    name: varchar("name", { length: 256 }).notNull(),
    providerId: varchar("provider_id", { length: 256 }).notNull(),
    providerName: varchar("provider_name", { length: 256 }).notNull(),
    url: varchar("url", { length: 256 }).notNull(),
    image: varchar("image", { length: 256 }).notNull(),
    score: integer("score"),
    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    unq: unique().on(t.providerName, t.providerId),
  })
);

// Schema for performers - used to validate API requests
const baseSchema = createSelectSchema(performers).omit(timestamps);

export const insertPerformerSchema = createInsertSchema(performers).omit(timestamps);
export const insertPerformerParams = baseSchema
  .extend({
    score: z.number().optional(),
  })
  .omit({
    id: true,
  });

export const updatePerformerSchema = baseSchema;
export const updatePerformerParams = baseSchema.omit({ score: true });
export const updatePerformerScoreParams = baseSchema.pick({ id: true, score: true });
export const performerIdSchema = baseSchema.pick({ id: true });

export const searchResultsParams = z.object({
  lat: z.number(),
  lng: z.number(),
  startDate: z.string(),
  endDate: z.string(),
  genres: z.array(z.string()),
  radius: z.number().default(50),
  searchType: z.enum(["venue", "agent"]),
});

export const performerWithEventsSearchParams = z.object({
  id: z.string(),
  lat: z.number(),
  lng: z.number(),
  startDate: z.string(),
  endDate: z.string(),
  radius: z.number().default(50),
});

// Types for performers - used to type API request params and within Components
export type Performer = typeof performers.$inferSelect;
export type NewPerformer = z.infer<typeof insertPerformerSchema>;
export type NewPerformerParams = z.infer<typeof insertPerformerParams>;
export type UpdatePerformerParams = z.infer<typeof updatePerformerParams>;
export type UpdatePerformerScoreParams = z.infer<typeof updatePerformerScoreParams>;
export type PerformerId = z.infer<typeof performerIdSchema>["id"];

// this type infers the return from getPerformers() - meaning it will include any joins
export type CompletePerformer = Awaited<ReturnType<typeof getPerformers>>["performers"][number];

export type PerformerWithEvents = {
  performer: Performer;
  events: Event[];
};
