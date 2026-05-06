import { sql } from "drizzle-orm";
import { varchar, timestamp, pgTable, unique } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getCronLocks } from "@/lib/api/cronLocks/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const cronLocks = pgTable(
  "cron_locks",
  {
    id: varchar("id", { length: 191 })
      .primaryKey()
      .$defaultFn(() => nanoid()),
    jobName: varchar("job_name", { length: 256 }).notNull(),
    lockedUntil: timestamp("locked_until").notNull(),

    createdAt: timestamp("created_at")
      .notNull()
      .default(sql`now()`),
    updatedAt: timestamp("updated_at")
      .notNull()
      .default(sql`now()`),
  },
  (t) => ({
    unq: unique().on(t.jobName),
  })
);

// Schema for cronLocks - used to validate API requests
const baseSchema = createSelectSchema(cronLocks).omit(timestamps);

export const insertCronLockSchema = createInsertSchema(cronLocks).omit(timestamps);
export const insertCronLockParams = baseSchema
  .extend({
    lockedUntil: z.coerce.string().min(1),
  })
  .omit({
    id: true,
  });

export const updateCronLockSchema = baseSchema;
export const updateCronLockParams = baseSchema.extend({
  lockedUntil: z.coerce.string().min(1),
});
export const cronLockIdSchema = baseSchema.pick({ id: true });

// Types for cronLocks - used to type API request params and within Components
export type CronLock = typeof cronLocks.$inferSelect;
export type NewCronLock = z.infer<typeof insertCronLockSchema>;
export type NewCronLockParams = z.infer<typeof insertCronLockParams>;
export type UpdateCronLockParams = z.infer<typeof updateCronLockParams>;
export type CronLockId = z.infer<typeof cronLockIdSchema>["id"];

// this type infers the return from getCronLocks() - meaning it will include any joins
export type CompleteCronLock = Awaited<ReturnType<typeof getCronLocks>>["cronLocks"][number];
