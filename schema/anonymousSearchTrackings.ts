import { sql } from "drizzle-orm";
import { varchar, integer, date, timestamp, pgTable, uniqueIndex, unique, index } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getAnonymousSearchTrackings } from "@/lib/api/anonymousSearchTrackings/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const anonymousSearchTrackings = pgTable(
  "anonymous_search_trackings",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    ipAddress: varchar("ip_address", { length: 256 }).notNull(),
    searchCount: integer("search_count").notNull(),
    resetDate: date("reset_date").notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (anonymousSearchTrackings) => ({
    uniqueIpDate: unique().on(anonymousSearchTrackings.ipAddress, anonymousSearchTrackings.resetDate),
    ipResetDateIdx: index("idx_ip_reset_date").on(
      anonymousSearchTrackings.ipAddress,
      anonymousSearchTrackings.resetDate
    ),
  })
);

// Schema for anonymousSearchTrackings - used to validate API requests
const baseSchema = createSelectSchema(anonymousSearchTrackings).omit(timestamps);

export const insertAnonymousSearchTrackingSchema = createInsertSchema(anonymousSearchTrackings).omit(timestamps);
export const insertAnonymousSearchTrackingParams = baseSchema
  .extend({
    searchCount: z.coerce.number(),
    resetDate: z.coerce.string().min(1),
  })
  .omit({
    id: true,
  });

export const updateAnonymousSearchTrackingSchema = baseSchema;
export const updateAnonymousSearchTrackingParams = baseSchema.extend({
  searchCount: z.coerce.number(),
  resetDate: z.coerce.string().min(1),
});
export const anonymousSearchTrackingIdSchema = baseSchema.pick({ id: true });

// Types for anonymousSearchTrackings - used to type API request params and within Components
export type AnonymousSearchTracking = typeof anonymousSearchTrackings.$inferSelect;
export type NewAnonymousSearchTracking = z.infer<typeof insertAnonymousSearchTrackingSchema>;
export type NewAnonymousSearchTrackingParams = z.infer<typeof insertAnonymousSearchTrackingParams>;
export type UpdateAnonymousSearchTrackingParams = z.infer<typeof updateAnonymousSearchTrackingParams>;
export type AnonymousSearchTrackingId = z.infer<typeof anonymousSearchTrackingIdSchema>["id"];

// this type infers the return from getAnonymousSearchTrackings() - meaning it will include any joins
export type CompleteAnonymousSearchTracking = Awaited<
  ReturnType<typeof getAnonymousSearchTrackings>
>["anonymousSearchTrackings"][number];
