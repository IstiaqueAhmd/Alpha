import { relations, sql } from "drizzle-orm";
import { varchar, date, real, timestamp, pgTable, unique, index } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getEvents } from "@/lib/api/events/queries";

import { nanoid, timestamps } from "@/lib/utils";
import { venues } from "./venues";

export const events = pgTable(
  "events",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    venueId: varchar("venue_id", { length: 191 }).references(() => venues.id),

    providerName: varchar("provider_name", { length: 256 }).notNull(),
    providerId: varchar("provider_id", { length: 256 }).notNull(),
    name: varchar("name", { length: 256 }).notNull(),
    url: varchar("url", { length: 256 }).notNull(),
    locationName: varchar("location_name", { length: 256 }).notNull(),
    locationUrl: varchar("location_url", { length: 256 }).notNull(),
    startDate: date("start_date").notNull(),
    endDate: date("end_date").notNull(),
    address: varchar("address", { length: 256 }).notNull(),
    lat: real("lat"),
    long: real("long"),
    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    dateRange: index().on(t.startDate, t.endDate),
    location: index().on(t.lat, t.long),
    unq: unique().on(t.providerName, t.providerId),
  })
);

export const eventsRelations = relations(events, ({ one }) => ({
  venue: one(venues, {
    fields: [events.venueId],
    references: [venues.id],
  }),
}));

// Schema for events - used to validate API requests
const baseSchema = createSelectSchema(events).omit(timestamps);

export const insertEventSchema = createInsertSchema(events).omit(timestamps);
export const insertEventParams = baseSchema
  .extend({
    startDate: z.coerce.string().min(1),
    endDate: z.coerce.string().min(1),
    // lat: z.coerce.number().optional(),
    // long: z.coerce.number().optional(),
  })
  .omit({
    id: true,
  });

export const updateEventSchema = baseSchema;
export const updateEventParams = baseSchema.extend({
  startDate: z.coerce.string().min(1),
  endDate: z.coerce.string().min(1),
  // lat: z.coerce.number().optional(),
  // long: z.coerce.number().optional(),
});
export const eventIdSchema = baseSchema.pick({ id: true });

// Types for events - used to type API request params and within Components
export type Event = typeof events.$inferSelect;
export type NewEvent = z.infer<typeof insertEventSchema>;
export type NewEventParams = z.infer<typeof insertEventParams>;
export type UpdateEventParams = z.infer<typeof updateEventParams>;
export type EventId = z.infer<typeof eventIdSchema>["id"];

// this type infers the return from getEvents() - meaning it will include any joins
export type CompleteEvent = Awaited<ReturnType<typeof getEvents>>["events"][number];
