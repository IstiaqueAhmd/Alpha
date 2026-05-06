import { sql } from "drizzle-orm";
import { varchar, timestamp, pgTable, unique, index } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";
import { performers } from "./performers";
import { events } from "./events";
import { type getPerformerEvents } from "@/lib/api/performerEvents/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const performerEvents = pgTable(
  "performer_events",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    performerId: varchar("performer_id", { length: 256 })
      .references(() => performers.id, { onDelete: "cascade" })
      .notNull(),
    eventId: varchar("event_id", { length: 256 })
      .references(() => events.id, { onDelete: "cascade" })
      .notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    performerId: index().on(t.performerId),
    eventId: index().on(t.eventId),
    unq: unique().on(t.performerId, t.eventId),
  })
);

// Schema for performerEvents - used to validate API requests
const baseSchema = createSelectSchema(performerEvents).omit(timestamps);

export const insertPerformerEventSchema = createInsertSchema(performerEvents).omit(timestamps);
export const insertPerformerEventParams = baseSchema
  .extend({
    performerId: z.coerce.string().min(1),
    eventId: z.coerce.string().min(1),
  })
  .omit({
    id: true,
  });

export const updatePerformerEventSchema = baseSchema;
export const updatePerformerEventParams = baseSchema.extend({
  performerId: z.coerce.string().min(1),
  eventId: z.coerce.string().min(1),
});
export const performerEventIdSchema = baseSchema.pick({ id: true });

// Types for performerEvents - used to type API request params and within Components
export type PerformerEvent = typeof performerEvents.$inferSelect;
export type NewPerformerEvent = z.infer<typeof insertPerformerEventSchema>;
export type NewPerformerEventParams = z.infer<typeof insertPerformerEventParams>;
export type UpdatePerformerEventParams = z.infer<typeof updatePerformerEventParams>;
export type PerformerEventId = z.infer<typeof performerEventIdSchema>["id"];

// this type infers the return from getPerformerEvents() - meaning it will include any joins
export type CompletePerformerEvent = Awaited<ReturnType<typeof getPerformerEvents>>["performerEvents"][number];
