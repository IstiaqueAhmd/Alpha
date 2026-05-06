import { sql } from "drizzle-orm";
import { varchar, integer, timestamp, pgTable, pgEnum, unique } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { users } from "@/lib/db/schema/auth";
import { type getUserProfiles } from "@/lib/api/userProfiles/queries";

import { nanoid, timestamps } from "@/lib/utils";
export const userProfileTypeEnum = pgEnum("user_profile_type", ["artist", "agent", "buyer", "venue", "other"]);
export const userProfiles = pgTable(
  "user_profiles",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    name: varchar("name", { length: 256 }).notNull(),
    type: userProfileTypeEnum("type").notNull(),
    venueSize: integer("venue_size"),
    website: varchar("website", { length: 256 }),
    address: varchar("address", { length: 256 }),
    favoritePerformers: varchar("favorite_performers", { length: 256 }).array(),
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
    unq: unique().on(t.userId),
  })
);

// Schema for userProfiles - used to validate API requests
const baseSchema = createSelectSchema(userProfiles).omit(timestamps);

export const insertUserProfileSchema = createInsertSchema(userProfiles).omit(timestamps);
export const insertUserProfileParams = baseSchema
  .extend({
    venueSize: z.coerce.number().optional(),
    favoritePerformers: z.array(z.string()).optional(),
  })
  .omit({
    id: true,
    userId: true,
  });

export const updateUserProfileSchema = baseSchema;
export const updateUserProfileParams = baseSchema.extend({}).omit({
  userId: true,
});

export const userProfileIdSchema = baseSchema.pick({ id: true });

// Types for userProfiles - used to type API request params and within Components
export type UserProfile = typeof userProfiles.$inferSelect;
export type NewUserProfile = z.infer<typeof insertUserProfileSchema>;
export type NewUserProfileParams = z.infer<typeof insertUserProfileParams>;
export type UpdateUserProfileParams = z.infer<typeof updateUserProfileParams>;
export type UserProfileId = z.infer<typeof userProfileIdSchema>["id"];

// this type infers the return from getUserProfiles() - meaning it will include any joins
export type CompleteUserProfile = Awaited<ReturnType<typeof getUserProfiles>>["userProfiles"][number];
