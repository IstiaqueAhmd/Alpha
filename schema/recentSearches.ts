import { sql } from "drizzle-orm";
import { text, varchar, timestamp, pgTable, unique } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { users } from "@/lib/db/schema/auth";
import { type getRecentSearches } from "@/lib/api/recentSearches/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const recentSearches = pgTable(
  "recent_searches",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    queryString: text("query_string").notNull(),
    displayName: varchar("display_name", { length: 256 }).notNull(),
    userId: varchar("user_id", { length: 256 })
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    unq: unique().on(t.displayName, t.userId),
  })
);

// Schema for recentSearches - used to validate API requests
const baseSchema = createSelectSchema(recentSearches).omit(timestamps);

export const insertRecentSearchSchema = createInsertSchema(recentSearches).omit(timestamps);
export const insertRecentSearchParams = baseSchema.extend({}).omit({
  id: true,
  userId: true,
});

export const updateRecentSearchSchema = baseSchema;
export const updateRecentSearchParams = baseSchema.extend({}).omit({
  userId: true,
});
export const recentSearchIdSchema = baseSchema.pick({ id: true });

// Types for recentSearches - used to type API request params and within Components
export type RecentSearch = typeof recentSearches.$inferSelect;
export type NewRecentSearch = z.infer<typeof insertRecentSearchSchema>;
export type NewRecentSearchParams = z.infer<typeof insertRecentSearchParams>;
export type UpdateRecentSearchParams = z.infer<typeof updateRecentSearchParams>;
export type RecentSearchId = z.infer<typeof recentSearchIdSchema>["id"];

// this type infers the return from getRecentSearches() - meaning it will include any joins
export type CompleteRecentSearch = Awaited<ReturnType<typeof getRecentSearches>>["recentSearches"][number];
