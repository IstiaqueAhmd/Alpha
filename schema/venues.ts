import { sql } from "drizzle-orm";
import { varchar, real, integer, timestamp, pgTable, index, unique } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { nanoid, timestamps } from "@/lib/utils";
import { getVenues } from "@/lib/api/venues/queries";

export const venues = pgTable(
  "venues",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    providerName: varchar("provider_name", { length: 256 }).notNull(),
    providerId: varchar("provider_id", { length: 256 }).notNull(),
    providerSlug: varchar("provider_slug", { length: 256 }).notNull(),
    providerUrl: varchar("provider_url", { length: 256 }).notNull(),
    name: varchar("name", { length: 256 }).notNull(),
    address: varchar("address", { length: 256 }).notNull(),
    city: varchar("city", { length: 256 }).notNull(),
    state: varchar("state", { length: 256 }).notNull(),
    postalCode: varchar("postal_code", { length: 256 }).notNull(),
    country: varchar("country", { length: 256 }).notNull(),
    lat: real("lat").notNull(),
    long: real("long").notNull(),
    capacity: integer("capacity").notNull(),
    score: real("score"),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    location: index().on(t.lat, t.long),
    unq: unique().on(t.providerName, t.providerId),
  })
);

// Schema for venues - used to validate API requests
const baseSchema = createSelectSchema(venues).omit(timestamps);

export const insertVenueSchema = createInsertSchema(venues).omit(timestamps);
export const insertVenueParams = baseSchema
  .extend({
    lat: z.coerce.number(),
    long: z.coerce.number(),
    capacity: z.coerce.number(),
    score: z.coerce.number(),
  })
  .omit({
    id: true,
  });

export const updateVenueSchema = baseSchema;
export const updateVenueParams = baseSchema.extend({
  lat: z.coerce.number(),
  long: z.coerce.number(),
  capacity: z.coerce.number(),
  score: z.coerce.number(),
});
export const venueIdSchema = baseSchema.pick({ id: true });

// Types for venues - used to type API request params and within Components
export type Venue = typeof venues.$inferSelect;
export type NewVenue = z.infer<typeof insertVenueSchema>;
export type NewVenueParams = z.infer<typeof insertVenueParams>;
export type UpdateVenueParams = z.infer<typeof updateVenueParams>;
export type VenueId = z.infer<typeof venueIdSchema>["id"];

// this type infers the return from getVenues() - meaning it will include any joins
export type CompleteVenue = Awaited<ReturnType<typeof getVenues>>["venues"][number];
